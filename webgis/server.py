"""Local FastAPI server for prepared vector tiles and feature records."""

from contextlib import asynccontextmanager, closing
import gzip
import json
import sqlite3

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from layers import LAYERS, ROOT, RUNTIME, search_text


def read_only(path):
    return closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True))


@asynccontextmanager
async def lifespan(app):
    catalog_path = RUNTIME / "catalog.json"
    if not catalog_path.is_file():
        raise RuntimeError("Chạy python -X utf8 build_data.py trước khi mở WebGIS.")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    # Presentation defaults can change independently of the prepared tile files.
    for entry in catalog["layers"]:
        style = LAYERS.get(entry["id"], entry)
        presentation = {name: style[name] for name in ("color", "visible", "outline") if name in style}
        entry.update(presentation)
    app.state.catalog = catalog
    app.state.layers = {entry["id"]: entry for entry in catalog["layers"]}
    app.state.directory = RUNTIME / catalog["version"]
    yield


app = FastAPI(title="Xác định vùng quy hoạch trồng lúa năng suất, chất lượng cao trên địa bàn tỉnh Đồng Tháp", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=ROOT / "static"), name="assets")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/maplibre/{asset}", include_in_schema=False)
def maplibre(asset: str):
    if asset not in {"maplibre-gl.mjs", "maplibre-gl-worker.mjs", "maplibre-gl.css"}:
        raise HTTPException(404)
    path = ROOT / "node_modules" / "maplibre-gl" / "dist" / asset
    if not path.is_file():
        raise HTTPException(503, "Chạy npm install trong thư mục webgis.")
    content_type = "text/css" if asset.endswith(".css") else "text/javascript"
    return FileResponse(path, media_type=content_type)


@app.get("/api/layers")
def list_layers():
    return app.state.catalog


def check_version(version):
    if version != app.state.catalog["version"]:
        raise HTTPException(404, "Phiên bản dữ liệu đã đổi. Hãy tải lại trang.")


def check_layer(layer):
    if layer not in app.state.layers:
        raise HTTPException(404, "Không có lớp dữ liệu này.")
    return app.state.layers[layer]


@app.get("/api/{version}/tiles/{layer}/{z}/{x}/{y}.pbf")
def tile(version: str, layer: str, z: int, x: int, y: int, request: Request):
    check_version(version)
    config = check_layer(layer)
    if not config["minzoom"] <= z <= config["maxzoom"] or not (
        0 <= x < 2**z and 0 <= y < 2**z
    ):
        raise HTTPException(404)
    headers = {"Cache-Control": "private, max-age=86400, immutable", "Vary": "Accept-Encoding"}
    with read_only(app.state.directory / f"{layer}.mbtiles") as db:
        row = db.execute("""
            SELECT tile_data FROM tiles
            WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?
        """, (z, x, 2**z - 1 - y)).fetchone()
    if row is None:
        return Response(content=b"", media_type="application/vnd.mapbox-vector-tile", headers=headers)
    content = row[0]
    if content.startswith(b"\x1f\x8b"):
        encodings = request.headers.get("Accept-Encoding", "").lower().split(",")
        accepts_gzip = any(
            coding.strip() == "gzip" and quality.strip().removeprefix("q=") not in {"0", "0.0", "0.00", "0.000"}
            for coding, _, quality in (value.partition(";") for value in encodings)
        )
        if accepts_gzip:
            headers["Content-Encoding"] = "gzip"
        else:
            content = gzip.decompress(content)
    return Response(content=content, media_type="application/vnd.mapbox-vector-tile", headers=headers)


@app.get("/api/{version}/features/{layer}/{fid}")
def feature(version: str, layer: str, fid: int):
    check_version(version)
    check_layer(layer)
    with read_only(app.state.directory / "attributes.sqlite") as db:
        row = db.execute(
            "SELECT label,properties,bounds FROM features WHERE layer=? AND fid=?", (layer, fid)
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Không tìm thấy đối tượng.")
    label, properties, bounds = row
    return {"layer": layer, "fid": fid, "label": label, "properties": json.loads(properties),
            "bounds": json.loads(bounds) if bounds else None}


@app.get("/api/{version}/search")
def search(version: str, q: str = Query(min_length=2, max_length=100),
           layer: str | None = None, limit: int = Query(default=12, ge=1, le=30)):
    check_version(version)
    if layer is not None:
        check_layer(layer)
    normalized = search_text(q)
    quoted = '"' + normalized.replace('"', '""') + '"'
    with read_only(app.state.directory / "attributes.sqlite") as db:
        id_text = normalized.removeprefix("#")
        if normalized.startswith("#") and id_text.isascii() and id_text.isdecimal() and len(id_text) < 16:
            rows = db.execute("""
                SELECT layer, fid, label, bounds FROM features
                WHERE fid = ? AND (? IS NULL OR layer = ?) ORDER BY layer LIMIT ?
            """, (int(id_text), layer, layer, limit)).fetchall()
        elif len(normalized) >= 3:
            rows = db.execute("""
                SELECT f.layer, f.fid, f.label, f.bounds
                FROM feature_search AS idx JOIN features AS f
                  ON f.layer=idx.layer AND f.fid=idx.fid
                WHERE idx.search MATCH ? AND (? IS NULL OR idx.layer = ?)
                ORDER BY (f.layer <> 'ranh-xa'), (f.search <> ?), length(f.search), f.layer, f.fid
                LIMIT ?
            """, (quoted, layer, layer, normalized, limit)).fetchall()
        else:
            return []
    return [{"layer": layer_id, "fid": fid, "label": label, "bounds": json.loads(bounds) if bounds else None}
            for layer_id, fid, label, bounds in rows]
