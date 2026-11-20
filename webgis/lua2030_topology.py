"""Create a non-overlapping Lua2030 coverage while retaining source feature IDs."""

import json

import geopandas as gpd
import numpy as np
import pyogrio
import shapely


GRID_METERS = 0.001
PRODUCT = "Lua2030_KhongChongDe.gpkg"


def merge_faces(pieces):
    if len(pieces) == 1:
        return pieces[0]
    merged = shapely.coverage_union_all(pieces)
    # A ring pinched at a single vertex can need the full polygon overlay.
    return merged if merged.is_valid else shapely.union_all(pieces)


def first_overlap(polygons):
    tree = shapely.STRtree(polygons)
    for start in range(0, len(polygons), 512):
        left, right = tree.query(polygons[start:start + 512], predicate="intersects")
        left += start
        pairs = left < right
        left, right = left[pairs], right[pairs]
        overlap = shapely.relate_pattern(polygons[left], polygons[right], "2********")
        if overlap.any():
            index = np.flatnonzero(overlap)[0]
            return left[index], right[index]
    return None


def remove_overlaps(frame, directory):
    if frame.crs.to_epsg() != 5897:
        raise ValueError("Xử lý lớp Lúa 2030 cần hệ chiếu nguồn EPSG:5897.")
    raw = frame.geometry.to_numpy()
    if not (shapely.is_valid(raw) & ~shapely.is_empty(raw)).all():
        raise ValueError("Lớp Lúa 2030 có hình học nguồn rỗng hoặc lỗi. Cần kiểm tra trước khi xử lý chồng đè.")

    print("Lúa 2030: dựng các vùng không chồng nhau trên lưới 1 mm…", flush=True)
    snapped = shapely.set_precision(raw, GRID_METERS)
    # Node the entire boundary network once. Both sides of every new boundary
    # then use the exact same coordinates, including at three-way intersections.
    network = shapely.union_all(shapely.boundary(snapped), grid_size=GRID_METERS)
    faces = shapely.get_parts(shapely.polygonize(shapely.get_parts(network)))
    del network

    face_indices, candidate_indices = shapely.STRtree(snapped).query(
        shapely.point_on_surface(faces), predicate="covered_by"
    )
    updated = frame["nguon_lop"].eq("Lua_truongxuan").fillna(False)
    general = frame["layer"].isin(("EraseDongThap", "EraseTienGiang"))
    # Retain the explicit commune update first. For overlaps with the CLC
    # records, retain attributes from the general rice records where present.
    priority = np.select([updated, general], [0, 1], default=2)
    order = np.lexsort((frame.index.to_numpy()[candidate_indices], priority[candidate_indices], face_indices))
    _, first = np.unique(face_indices[order], return_index=True)
    chosen = order[first]
    by_owner = chosen[np.argsort(candidate_indices[chosen], kind="stable")]
    owners = candidate_indices[by_owner]
    kept_indices, starts = np.unique(owners, return_index=True)
    kept_faces = faces[face_indices[by_owner]]
    if not len(kept_indices):
        raise ValueError("Không xác định được vùng Lúa 2030 trên lưới xử lý.")
    polygons = np.array([merge_faces(pieces) for pieces in np.split(kept_faces, starts[1:])], dtype=object)

    invalid = ~(shapely.is_valid(polygons) & ~shapely.is_empty(polygons))
    if invalid.any():
        ids = frame.index.to_numpy()[kept_indices[invalid]][:5]
        reasons = shapely.is_valid_reason(polygons[invalid][:5])
        raise ValueError(f"Lớp Lúa 2030 sau xử lý còn {invalid.sum()} hình học lỗi. Ví dụ {list(zip(ids, reasons))}")
    edge_matched = bool(shapely.coverage_is_valid(polygons))
    if not edge_matched:
        # Collinear vertices can be retained on one side only after regrouping
        # faces. Check interiors separately from exact common-edge segmentation.
        overlap = first_overlap(polygons)
        if overlap is not None:
            ids = frame.index.to_numpy()[kept_indices[list(overlap)]]
            raise ValueError(f"Lớp Lúa 2030 còn chồng đè ở cặp ID {ids.tolist()}.")
    print(f"Lúa 2030: {len(polygons):,} vùng đạt kiểm tra topology. Đang đối chiếu phạm vi phủ…", flush=True)
    expected = shapely.union_all(snapped, grid_size=GRID_METERS)
    actual = shapely.coverage_union_all(polygons) if edge_matched else shapely.union_all(polygons)
    mismatch = shapely.symmetric_difference(expected, actual, grid_size=GRID_METERS).area
    # Both coverages use a millimetre grid. Bound any area changes at snapped intersections.
    if mismatch > 1000:
        raise ValueError(f"Phạm vi phủ sau xử lý lệch {mismatch:.3f} m² so với hợp vùng nguồn.")

    cleaned = frame.iloc[kept_indices].copy()
    cleaned.geometry = gpd.GeoSeries(polygons, index=cleaned.index, crs=frame.crs)
    cleaned["dien_tich_ha_nguon"] = cleaned["dien_tich_ha"]
    cleaned["dien_tich_ha"] = cleaned.geometry.area / 10_000
    cleaned["gpkg_id"] = cleaned.index.to_numpy()
    pyogrio.write_dataframe(
        cleaned, directory / PRODUCT, layer="Lua2030", promote_to_multi=True,
        layer_options={"FID": "gpkg_id"},
    )
    cleaned.drop(columns="gpkg_id", inplace=True)

    area_before = float(shapely.area(raw).sum() / 10_000)
    area_after = float(shapely.area(polygons).sum() / 10_000)
    audit = {
        "product": PRODUCT,
        "grid_m": GRID_METERS,
        "source_count": len(raw),
        "published_count": len(polygons),
        "removed_count": len(raw) - len(polygons),
        "source_sum_ha": area_before,
        "source_union_ha": expected.area / 10_000,
        "published_sum_ha": area_after,
        "source_excess_ha": float(shapely.area(snapped).sum() - expected.area) / 10_000,
        "footprint_difference_m2": mismatch,
        "no_interior_overlaps": True,
        "edge_matched": edge_matched,
    }
    (directory / "lua-2030-topology.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Lúa 2030: {area_after:,.4f} ha sau xử lý, chênh phạm vi phủ {mismatch:.4f} m².", flush=True)
    return cleaned, audit
