"""Build a versioned, read-only WebGIS snapshot from the project inputs."""

import argparse
from contextlib import closing
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
from shutil import copy2
import sqlite3
from tempfile import TemporaryDirectory
import uuid
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from pyproj import Transformer
from pyproj.transformer import TransformerGroup
import shapely
from shapely.geometry import MultiPolygon

from layers import (CONVERSION_PURPOSES, NON_AGRICULTURAL_PURPOSES, INPUT, REFERENCE,
                    RUNTIME, LAYERS, MAX_ZOOM, MIN_ZOOM, search_text)
from lua2030_pa import PRODUCT as PA_RICE_PRODUCT, WORKBOOK, apply_pa2030, commune_key
from lua2030_topology import PRODUCT as CLEAN_RICE_PRODUCT, remove_overlaps
from rice_actual import WORKBOOK as ACTUAL_WORKBOOK, read_actual_areas


DETAIL_LAYERS = ("chuyen-doi-2030", "phi-nn-2030", "lua-kiem-ke", "lua-thuc-te")


def transform(frame, target):
    source = frame.crs.to_epsg()
    if source == target:
        return frame
    operations = TransformerGroup(source, target, always_xy=True, allow_ballpark=False)
    if not operations.best_available or not operations.transformers:
        raise ValueError(f"Không có phép chuyển đổi phù hợp EPSG:{source} → EPSG:{target}")
    geometry = shapely.transform(
        frame.geometry.array, operations.transformers[0].transform, interleaved=False
    )
    return frame.set_geometry(gpd.GeoSeries(geometry, index=frame.index, crs=target))


def polygonal(geometry):
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type in {"GeometryCollection", "MultiPolygon"}:
        return [polygon for part in geometry.geoms for polygon in polygonal(part)]
    return []


def read_source(config, scratch):
    if "member" not in config:
        path = INPUT / config["source"]
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            table, = db.execute("SELECT table_name FROM gpkg_geometry_columns").fetchone()
        return path, pyogrio.read_dataframe(
            path, layer=table, columns=None if config.get("remove_overlaps") else config.get("source_fields", list(config["fields"])),
            fid_as_index=True,
        )

    member = config["member"]
    with zipfile.ZipFile(REFERENCE) as bundle:
        content = bundle.read(f"data/{member}.zip")
    with zipfile.ZipFile(BytesIO(content)) as archive:
        for suffix in (".shp", ".dbf", ".shx", ".prj", ".cpg"):
            filename = member + suffix
            (scratch / filename).write_bytes(archive.read(filename))
    frame = pyogrio.read_dataframe(
        scratch / (member + ".shp"), columns=list(config["fields"]), fid_as_index=True
    )
    return REFERENCE, frame


def assign_communes(frame, scratch):
    _, boundaries = read_source(LAYERS["ranh-xa"], scratch)
    boundaries = transform(boundaries, 5897)
    shapes = transform(frame, 5897).geometry.to_numpy().copy()
    invalid = ~shapely.is_valid(shapes) & ~shapely.is_missing(shapes)
    shapes[invalid] = shapely.make_valid(shapes[invalid])
    communes = boundaries.geometry.to_numpy()
    tree = shapely.STRtree(communes)
    feature_idx, commune_idx = tree.query(shapes, predicate="intersects")
    areas = shapely.area(shapely.intersection(shapes[feature_idx], communes[commune_idx]))
    match = areas > 0
    feature_idx, commune_idx, areas = feature_idx[match], commune_idx[match], areas[match]
    order = np.lexsort((commune_idx, -areas, feature_idx))
    _, first = np.unique(feature_idx[order], return_index=True)
    best = order[first]
    names = boundaries["TenXa"].to_numpy()
    assigned = np.full(len(shapes), "Chưa xác định", dtype=object)
    assigned[feature_idx[best]] = names[commune_idx[best]]
    # Handle sub-metre offsets between the two source layers at the commune boundary.
    unmatched = np.flatnonzero((assigned == "Chưa xác định") & shapely.is_valid(shapes) & ~shapely.is_empty(shapes))
    if len(unmatched):
        nearest = tree.nearest(shapes[unmatched])
        nearby = shapely.distance(shapes[unmatched], communes[nearest]) <= 1
        if "tenXa" in frame:
            source_names = frame["tenXa"].to_numpy()[unmatched]
            confirmed = np.array([
                isinstance(source, str) and commune_key(source) == commune_key(boundary)
                for source, boundary in zip(source_names, names[nearest])
            ])
            nearby |= confirmed
        assigned[unmatched[nearby]] = names[nearest[nearby]]
    return assigned


def non_agricultural_purpose(raw_code, map_code):
    primary = raw_code.split("(", 1)[0].strip().upper() if isinstance(raw_code, str) else ""
    alternate = map_code.strip().upper() if isinstance(map_code, str) else ""
    if primary and alternate and primary != alternate:
        return "Chưa xác định"
    return NON_AGRICULTURAL_PURPOSES.get(primary or alternate, "Chưa xác định")


def detail_attributes(layer_id, frame, scratch):
    frame["ten_xa_web"] = assign_communes(frame, scratch)
    if layer_id == "chuyen-doi-2030":
        frame["muc_dich_web"] = [
            " / ".join(CONVERSION_PURPOSES.get(code.strip(), "Chưa xác định") for code in value.upper().split("/"))
            if isinstance(value, str) and value.strip() else "Chưa xác định"
            for value in frame["ma_loai_dat"]
        ]
    elif layer_id == "phi-nn-2030":
        frame["muc_dich_web"] = [non_agricultural_purpose(raw, palette)
                                for raw, palette in zip(frame["maLoaiDat"], frame["MaMau"])]
    elif layer_id == "lua-kiem-ke":
        frame["loai_dat_web"] = frame["MaLD_HT"].map({"LUC": "Đất chuyên trồng lúa"}).fillna("Chưa xác định")
    else:
        totals, provenance = read_actual_areas(INPUT.parent / ACTUAL_WORKBOOK)
        frame["dien_tich_xa_web"] = [totals.get(commune_key(name), "Chưa có số liệu") for name in frame["ten_xa_web"]]
        return provenance
    return None


def store_attributes(layer_id, frame, config, extents, db):
    records = []
    for fid, attributes in frame.drop(columns=frame.geometry.name).iterrows():
        raw = {
            key: val for key, val in attributes.items()
            if pd.notna(val) and (not isinstance(val, str) or val.strip())
        }
        search_values = " · ".join(str(raw[key]) for key in config["search"] if key in raw)
        label = raw.get("ten_xa_web", search_values)
        properties = [{"label": config["fields"][key], "value": val}
                      for key, val in raw.items() if key in config["fields"]]
        records.append((layer_id, int(fid), label, search_text(search_values), json.dumps(
            properties, ensure_ascii=False, allow_nan=False
        ), extents.get(fid)))
    db.executemany("INSERT INTO features VALUES (?, ?, ?, ?, ?, ?)", records)


def refresh_detail_fields(layer_id, previous, entry, directory, scratch, db):
    config = LAYERS[layer_id]
    path, frame = read_source(config, scratch)
    with path.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != entry["sha256"]:
            raise ValueError(f"Nguồn lớp {layer_id} đã thay đổi so với bộ ô hiện có.")
    extents = dict(db.execute("SELECT fid,bounds FROM previous.features WHERE layer=?", (layer_id,)))
    if set(extents) != set(frame.index):
        raise ValueError(f"ID lớp {layer_id} không khớp với bộ ô hiện có.")
    provenance = detail_attributes(layer_id, frame, scratch)
    store_attributes(layer_id, frame, config, extents, db)
    copy2(previous / f"{layer_id}.mbtiles", directory / f"{layer_id}.mbtiles")
    if provenance is not None:
        entry = {**entry, "details_workbook": provenance}
    print(f"Đã cập nhật trường tra cứu {layer_id}: {len(frame):,} bản ghi", flush=True)
    return entry


def build_layer(layer_id, config, directory, scratch, db, hashes, clean_snapshot=None):
    if clean_snapshot is None:
        path, frame = read_source(config, scratch)
    else:
        path = INPUT / config["source"]
        frame = pyogrio.read_dataframe(clean_snapshot / CLEAN_RICE_PRODUCT, layer="Lua2030", fid_as_index=True)
    if frame.crs.to_epsg() != config["epsg"]:
        raise ValueError(f"Hệ tọa độ của {layer_id} khác cấu hình")
    if path not in hashes:
        with path.open("rb") as source:
            hashes[path] = hashlib.file_digest(source, "sha256").hexdigest()

    topology = None
    reconciliation = None
    if config.get("remove_overlaps"):
        if clean_snapshot is None:
            frame, topology = remove_overlaps(frame, directory)
        else:
            old_catalog = json.loads((RUNTIME / "catalog.json").read_text(encoding="utf-8"))
            entry = next(item for item in old_catalog["layers"] if item["id"] == layer_id)
            if old_catalog["version"] != clean_snapshot.name or entry["sha256"] != hashes[path]:
                raise ValueError("Lớp nguồn đã thay đổi. Hãy tạo lại lớp Lúa 2030 từ nguồn.")
            report = "lua-2030-topology.json"
            topology = json.loads((clean_snapshot / report).read_text(encoding="utf-8"))
            for name in (CLEAN_RICE_PRODUCT, report):
                copy2(clean_snapshot / name, directory / name)
        _, boundaries = read_source(LAYERS["ranh-xa"], scratch)
        frame, reconciliation = apply_pa2030(
            frame, transform(boundaries, 5897), INPUT.parent / WORKBOOK, directory, polygonal
        )
        columns = list(dict.fromkeys([*config["fields"], *config["search"]]))
        frame = frame[[*columns, frame.geometry.name]]
    provenance = detail_attributes(layer_id, frame, scratch) if layer_id in DETAIL_LAYERS else None

    geometry = frame.geometry
    present = geometry.notna() & ~geometry.is_empty
    invalid_at_source = present & ~geometry.is_valid
    projected = transform(frame.loc[present].copy(), 3857)
    invalid = ~projected.geometry.is_valid
    for fid, repaired in projected.geometry[invalid].make_valid().items():
        projected.at[fid, projected.geometry.name] = (
            MultiPolygon(polygonal(repaired)) if config["kind"] != "line" else repaired
        )
    projected = projected.loc[~projected.geometry.is_empty]
    if projected.empty or not projected.geometry.is_valid.all():
        raise ValueError(f"Không tạo được hình học hiển thị hợp lệ cho {layer_id}")

    # A millimetre grid removes round-off fragments before GDAL clips and quantizes the tiles.
    projected.geometry = projected.geometry.set_precision(0.001)
    projected = projected.loc[~projected.geometry.is_empty]
    bounds = projected.bounds
    wgs84 = Transformer.from_crs(3857, 4326, always_xy=True)
    for x, y in (("minx", "miny"), ("maxx", "maxy")):
        bounds[x], bounds[y] = wgs84.transform(bounds[x].to_numpy(), bounds[y].to_numpy())
    catalogue = {
        "id": layer_id, **{key: config[key] for key in (
            "source", "epsg", "label", "short", "group", "description", "color", "kind", "visible"
        )},
        "count": len(frame), "mapped": len(projected), "repaired": int(invalid.sum()),
        "invalid_at_source": int(invalid_at_source.sum()),
        "sha256": hashes[path], "bounds": [
            bounds.minx.min(), bounds.miny.min(), bounds.maxx.max(), bounds.maxy.max(),
        ],
        "minzoom": MIN_ZOOM, "maxzoom": MAX_ZOOM,
    }
    if topology:
        catalogue["topology"] = topology
    if reconciliation:
        catalogue["reconciliation"] = reconciliation
    if provenance:
        catalogue["details_workbook"] = provenance

    # Keep full display properties off the tile payload. Only the categorized layer needs a code.
    tile_frame = gpd.GeoDataFrame(
        {"feature_id": projected.index.to_numpy(), "geometry": projected.geometry.to_numpy()},
        crs=projected.crs,
    )
    if "categories" in config:
        field = config["category_field"]
        palette = config["categories"]
        source_codes = frame[field].str.strip().str.upper()
        tile_frame["land_code"] = source_codes.loc[projected.index].to_numpy()
        tile_frame = tile_frame.loc[tile_frame["land_code"].isin(palette)]
        counts = source_codes.value_counts()
        catalogue["categories"] = [
            {"code": code, "color": color, "count": int(counts.get(code, 0))}
            for code, color in palette.items()
        ]
    if "outline" in config:
        catalogue["outline"] = config["outline"]
    catalogue["tile_eligible"] = len(tile_frame)
    tiles = directory / f"{layer_id}.mbtiles"
    pyogrio.write_dataframe(
        tile_frame, tiles, driver="MBTiles", layer="features",
        dataset_options={
            "MINZOOM": MIN_ZOOM, "MAXZOOM": MAX_ZOOM, "MAX_SIZE": 500_000,
            "MAX_FEATURES": 200_000, "EXTENT": 8192, "BUFFER": 160,
            "SIMPLIFICATION": 2, "SIMPLIFICATION_MAX_ZOOM": 0,
            "TEMPORARY_DB": str(scratch / f"{layer_id}-gdal.sqlite"),
        },
    )
    with closing(sqlite3.connect(tiles.resolve().as_uri() + "?mode=ro", uri=True)) as archive:
        zooms = archive.execute(
            "SELECT zoom_level,count(*),max(length(tile_data)) FROM tiles GROUP BY zoom_level"
        ).fetchall()
    if not zooms or zooms[0][0] != MIN_ZOOM or zooms[-1][0] != MAX_ZOOM:
        raise ValueError(f"Thiếu dải mức zoom của {layer_id}")
    catalogue["tiles"] = sum(count for _, count, _ in zooms)
    catalogue["largest_tile_bytes"] = max(size for _, _, size in zooms)
    catalogue["tile_bytes"] = tiles.stat().st_size

    extents = {fid: json.dumps(list(row)) for fid, *row in bounds.itertuples()}
    store_attributes(layer_id, frame, config, extents, db)
    print(f"{layer_id}: {len(frame):,} bản ghi, {len(projected):,} hình học, "
          f"{int(invalid.sum()):,} cần sửa, {catalogue['tiles']:,} ô", flush=True)
    return catalogue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh-lua-2030", action="store_true", help="Giữ dữ liệu đã tạo của các lớp khác.")
    mode.add_argument("--apply-pa2030", action="store_true", help="Áp PA2030-IN cho hình học Lúa 2030 đã xử lý.")
    mode.add_argument("--refresh-conversion-fields", action="store_true", help="Cập nhật trường tra cứu lớp Chuyển đổi lúa.")
    mode.add_argument("--refresh-detail-fields", nargs="+", choices=DETAIL_LAYERS,
                      help="Cập nhật trường tra cứu của các lớp được chọn.")
    args = parser.parse_args()
    current = None
    refresh_fields = args.refresh_detail_fields or (["chuyen-doi-2030"] if args.refresh_conversion_fields else [])
    selected = refresh_fields or ["lua-2030"]
    if args.refresh_lua_2030 or args.apply_pa2030 or refresh_fields:
        current = json.loads((RUNTIME / "catalog.json").read_text(encoding="utf-8"))
        existing_entries = {entry["id"]: entry for entry in current["layers"]}
        previous = RUNTIME / current["version"]

    release = uuid.uuid4().hex
    directory = RUNTIME / release
    directory.mkdir(parents=True)
    database = directory / "attributes.sqlite"
    with TemporaryDirectory() as work_dir, closing(sqlite3.connect(database.as_uri(), uri=True)) as db, db:
        db.executescript("""
            CREATE TABLE features(
                layer TEXT NOT NULL, fid INTEGER NOT NULL, label TEXT NOT NULL,
                search TEXT NOT NULL, properties TEXT NOT NULL, bounds TEXT,
                PRIMARY KEY(layer, fid)
            ) WITHOUT ROWID;
            CREATE VIRTUAL TABLE feature_search USING fts5(
                layer UNINDEXED, fid UNINDEXED, search, tokenize='trigram'
            );
        """)
        hashes = {}
        catalogue = []
        if current:
            db.execute("ATTACH DATABASE ? AS previous", (previous.joinpath("attributes.sqlite").as_uri() + "?mode=ro",))
            placeholders = ",".join("?" for _ in selected)
            db.execute(f"INSERT INTO features SELECT * FROM previous.features WHERE layer NOT IN ({placeholders})", selected)
        for key, config in LAYERS.items():
            if key in refresh_fields:
                entry = refresh_detail_fields(key, previous, existing_entries[key], directory, Path(work_dir), db)
            elif current and key not in selected:
                entry = existing_entries[key]
                copy2(previous / f"{key}.mbtiles", directory / f"{key}.mbtiles")
                if key == "lua-2030":
                    for name in (CLEAN_RICE_PRODUCT, PA_RICE_PRODUCT, "lua-2030-topology.json", "lua-2030-pa2030.json"):
                        if (previous / name).is_file():
                            copy2(previous / name, directory / name)
            else:
                entry = build_layer(key, config, directory, Path(work_dir), db, hashes,
                                    clean_snapshot=previous if args.apply_pa2030 else None)
            catalogue.append(entry)
        db.execute("""
            INSERT INTO feature_search(layer, fid, search)
            SELECT layer, fid, search FROM features WHERE search <> '' AND bounds IS NOT NULL
        """)
    catalog = {"version": release, "layers": catalogue}
    pending = RUNTIME / f"{release}.json"
    pending.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(pending, RUNTIME / "catalog.json")
    print(f"Bản dữ liệu sẵn sàng: {release}", flush=True)


if __name__ == "__main__":
    main()
