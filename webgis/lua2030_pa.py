"""Publish Lua2030 by commune using the PA2030-IN targets."""

from contextlib import closing
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from io import BytesIO
import json
import unicodedata

import geopandas as gpd
import numpy as np
from openpyxl import load_workbook
import pyogrio
import shapely

from layers import search_text


WORKBOOK = "SL-CHUYEN DOI LUA-DONGTHAP-T11-2026-v1.xlsx"
SHEET = "PA2030-IN"
PRODUCT = "Lua2030_PA2030.gpkg"


def commune_key(name):
    key = " ".join(unicodedata.normalize("NFC", name).casefold().split())
    return "phường sơn qui" if key == "phường sơn quy" else key


def cents(value):
    return int((Decimal(str(value)) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def read_targets(content):
    targets = {}
    with closing(load_workbook(BytesIO(content), read_only=True, data_only=True)) as workbook:
        sheet = workbook[SHEET]
        if search_text(sheet["F5"].value or "") != "tong dien tich lua giu lai den nam 2030":
            raise ValueError("Không tìm thấy tiêu đề diện tích lúa giữ lại tại PA2030-IN!F5.")
        province_total = cents(sheet["F11"].value)
        for row, (number, name, _, _, _, area) in enumerate(
            sheet.iter_rows(min_row=12, max_col=6, values_only=True), 12
        ):
            if not isinstance(number, int):
                continue
            if not isinstance(name, str) or not isinstance(area, (int, float)) or area < 0:
                raise ValueError(f"Giá trị xã/phường hoặc diện tích không hợp lệ tại dòng {row}.")
            key = commune_key(name)
            if key in targets:
                raise ValueError(f"Trùng tên xã/phường ở dòng {row}: {name}")
            targets[key] = {"number": number, "name": name.strip(), "cell": f"F{row}", "target_cents": cents(area)}
    return targets, province_total


def apportion(target, areas, ids):
    # Integer weights in square millimetres and results in hundredths of a hectare.
    weights = [max(1, round(area * 1_000_000)) for area in areas]
    total = sum(weights)
    parts = [divmod(weight * target, total) for weight in weights]
    result = np.array([whole for whole, _ in parts], dtype=np.int64)
    order = sorted(range(len(parts)), key=lambda i: (-parts[i][1], ids[i]))
    for index in order[:target - int(result.sum())]:
        result[index] += 1
    return result


def clip_to_communes(frame, boundaries, targets):
    communes = [commune_key(name) for name in boundaries["TenXa"]]
    if len(set(communes)) != len(communes) or set(communes) != set(targets):
        raise ValueError("Danh sách xã/phường trong Excel và lớp ranh không khớp.")
    boundary_shapes = boundaries.geometry.to_numpy()
    if not shapely.coverage_is_valid(boundary_shapes):
        raise ValueError("Lớp ranh xã/phường có vùng trùng hoặc cạnh chung không khớp.")
    rice = frame.geometry.to_numpy()
    source_idx, commune_idx = shapely.STRtree(boundary_shapes).query(rice, predicate="intersects")
    pieces = shapely.intersection(rice[source_idx], boundary_shapes[commune_idx])
    areas = shapely.area(pieces)
    inclusion = np.array([targets[key]["target_cents"] > 0 for key in communes])
    keep = (areas > 0) & inclusion[commune_idx]
    removed_zero_m2 = float(areas[~inclusion[commune_idx]].sum())
    outside_m2 = float(shapely.area(rice).sum() - areas.sum())

    source_idx, commune_idx, pieces, areas = source_idx[keep], commune_idx[keep], pieces[keep], areas[keep]
    if not len(pieces):
        raise ValueError("Không có hình học Lúa 2030 trong các xã/phường có chỉ tiêu dương.")
    source_ids = frame.index.to_numpy()[source_idx]
    # Preserve the source ID for its largest retained part. Allocate new IDs
    # to the other parts in stable order by source ID and workbook sequence.
    numbers = np.array([targets[key]["number"] for key in communes], dtype=np.int64)
    order = np.lexsort((numbers[commune_idx], -areas, source_ids))
    source_idx, commune_idx, pieces, areas, source_ids = (
        values[order] for values in (source_idx, commune_idx, pieces, areas, source_ids)
    )
    ids = source_ids.copy()
    additional = np.r_[False, source_ids[1:] == source_ids[:-1]]
    ids[additional] = np.arange(frame.index.max() + 1, frame.index.max() + 1 + int(additional.sum()))
    allocated = np.zeros(len(pieces), dtype=np.int64)
    rows = []
    for index, key in enumerate(communes):
        record = targets[key]
        members = np.flatnonzero(commune_idx == index)
        target = record["target_cents"]
        if target > 0 and not len(members):
            raise ValueError(f"Không có vùng lúa cho {record['name']} dù Excel giao diện tích dương.")
        if len(members):
            allocated[members] = apportion(target, areas[members], ids[members])
        actual = int(allocated[members].sum())
        if actual != target:
            raise ValueError(f"Chưa cân bằng diện tích của {record['name']}.")
        rows.append({**record, "allocated_cents": actual, "features": len(members),
                     "geometry_ha": float(areas[members].sum() / 10_000)})

    result = frame.iloc[source_idx].copy()
    result.index = ids
    result.geometry = gpd.GeoSeries(pieces, index=result.index, crs=frame.crs)
    result["id_nguon_pa2030"] = source_ids
    result["ten_xa_web"] = [targets[communes[index]]["name"] for index in commune_idx]
    result["dien_tich_ha"] = areas / 10_000
    result["dien_tich_web_ha"] = allocated / 100
    return result, rows, removed_zero_m2, outside_m2


def apply_pa2030(frame, boundaries, path, directory, polygonal):
    print("Lúa 2030: áp chỉ tiêu theo từng xã/phường từ PA2030-IN…", flush=True)
    content = path.read_bytes()
    targets, province_total = read_targets(content)
    result, rows, removed_zero_m2, outside_m2 = clip_to_communes(frame, boundaries, targets)
    mixed = ~result.geom_type.isin(["Polygon", "MultiPolygon"])
    for fid, geometry in result.geometry[mixed].items():
        result.at[fid, result.geometry.name] = shapely.MultiPolygon(polygonal(geometry))
    if not (result.geometry.is_valid & ~result.geometry.is_empty).all():
        raise ValueError("Có hình học lỗi sau khi cắt Lúa 2030 theo ranh xã.")
    result["gpkg_id"] = result.index
    pyogrio.write_dataframe(result, directory / PRODUCT, layer="Lua2030", promote_to_multi=True,
                            layer_options={"FID": "gpkg_id"})
    result.drop(columns="gpkg_id", inplace=True)
    source_hash = hashlib.sha256(content).hexdigest()
    metrics = {
        "workbook": path.name, "workbook_sha256": source_hash, "sheet": SHEET, "product": PRODUCT,
        "communes": len(rows), "positive_communes": sum(row["target_cents"] > 0 for row in rows),
        "sum_displayed_cents": sum(row["allocated_cents"] for row in rows),
        "province_cell_cents": province_total,
        "removed_zero_ha": removed_zero_m2 / 10_000,
        "outside_commune_boundaries_ha": outside_m2 / 10_000,
        "published_count": len(result),
    }
    (directory / "lua-2030-pa2030.json").write_text(
        json.dumps({"summary": metrics, "communes": sorted(rows, key=lambda row: row["number"])},
                   ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result, metrics
