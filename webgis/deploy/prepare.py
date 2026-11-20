"""Package the prepared WebGIS snapshot for Cloudflare and the x10 HTML host."""

import argparse
from collections import defaultdict
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from layers import LAYERS, ROOT, RUNTIME


BLOCK_SIZE = 128
SEARCH_LIMIT = 30
CHUNK_SIZE = 256 * 1024
HOST_ORIGIN = "https://chuyendoiluadongthap.x10.mx"
ACCOUNT_ID = "6f7e7a5e44d4f7627b6ba481f9df02c1"
DATABASE_NAME = "dong-thap-webgis-attributes"
WORKER_NAME = "dong-thap-lua-webgis"
CATALOG_FIELDS = (
    "id", "label", "short", "group", "description", "color", "kind", "visible",
    "count", "bounds", "minzoom", "maxzoom", "outline", "categories",
)


def json_bytes(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def public_catalog(snapshot):
    layers = []
    for entry in snapshot["layers"]:
        layer_id = entry["id"]
        style = LAYERS[layer_id]
        public = {name: entry[name] for name in CATALOG_FIELDS if name in entry}
        public.update({name: style[name] for name in ("color", "visible", "outline") if name in style})
        if entry["kind"] != "polygon":
            public.update(source=entry["source"], epsg=entry["epsg"])
        layers.append(public)
    return {"version": snapshot["version"], "layers": layers}


def sql_text(value):
    return "'" + value.replace("'", "''") + "'"


def write_block(sql, version, key, records):
    layer, block = key
    payload = sql_text(json_bytes(records).decode("utf-8"))
    statement = (f"INSERT OR REPLACE INTO feature_blocks VALUES "
                 f"({sql_text(version)},{sql_text(layer)},{block},{len(records)},{payload});\n")
    if len(statement.encode("utf-8")) > 95_000:
        raise ValueError(f"D1 SQL statement too large: {layer}, block {block}")
    sql.write(statement)


def export_attributes(source, directory, version):
    search_groups = defaultdict(list)
    count = 0
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute("SELECT layer,fid,label,search,properties,bounds FROM features ORDER BY layer,fid")
        with (directory / "attributes.sql").open("w", encoding="utf-8", newline="\n") as sql:
            sql.write(
                "CREATE TABLE IF NOT EXISTS feature_blocks (version TEXT NOT NULL, "
                "layer TEXT NOT NULL, block INTEGER NOT NULL, feature_count INTEGER NOT NULL, "
                "records TEXT NOT NULL, PRIMARY KEY (version,layer,block)) WITHOUT ROWID;\n"
            )
            block = {}
            previous_key = None
            for layer, fid, label, search, properties, bounds in rows:
                key = (layer, fid // BLOCK_SIZE)
                if key != previous_key and previous_key is not None:
                    write_block(sql, version, previous_key, block)
                    block = {}
                previous_key = key
                block[fid] = [label, json.loads(properties), json.loads(bounds) if bounds else None]
                matches = search_groups[(layer, search)]
                if search and len(matches) < SEARCH_LIMIT:
                    matches.append(fid)
                count += 1
            if previous_key is not None:
                write_block(sql, version, previous_key, block)
    search_entries = defaultdict(list)
    for (layer, query), ids in search_groups.items():
        if ids:
            search_entries[layer].append([query, ids])
    return search_entries, count


def split_tiles(catalog, source, directory, pmtiles):
    version = catalog["version"]
    archive_dir = directory / "pmtiles"
    archive_dir.mkdir(parents=True, exist_ok=True)
    asset_dir = directory / "cloudflare-assets"
    total = 0
    for layer in catalog["layers"]:
        name = layer["id"]
        archive = archive_dir / f"{name}.pmtiles"
        if not archive.exists():
            cached = directory / "r2" / f"{version}-{name}.pmtiles"
            if cached.is_file():
                archive = cached
            else:
                partial = archive.with_suffix(".partial.pmtiles")
                subprocess.run([str(pmtiles), "convert", str(source / f"{name}.mbtiles"), str(partial)], check=True)
                partial.replace(archive)
        subprocess.run([str(pmtiles), "verify", str(archive)], check=True)
        path = f"/map/{version}/{name}"
        target = asset_dir / path.lstrip("/")
        target.mkdir(parents=True, exist_ok=True)
        with archive.open("rb") as stream:
            chunks = 0
            while chunk := stream.read(CHUNK_SIZE):
                (target / f"{chunks}.bin").write_bytes(chunk)
                chunks += 1
            total += chunks
        layer["tileArchive"] = {"path": path, "size": archive.stat().st_size, "chunkSize": CHUNK_SIZE}
    catalog_file = asset_dir / "api" / "layers"
    catalog_file.parent.mkdir(exist_ok=True)
    catalog_file.write_bytes(json_bytes(catalog))
    (asset_dir / "_headers").write_text(
        f"/map/*\n  Access-Control-Allow-Origin: {HOST_ORIGIN}\n"
        "  Cache-Control: public, max-age=31536000, immutable\n"
        "  X-Content-Type-Options: nosniff\n"
        f"/api/layers\n  Access-Control-Allow-Origin: {HOST_ORIGIN}\n"
        "  Content-Type: application/json; charset=utf-8\n"
        "  Cache-Control: public, max-age=60\n",
        encoding="utf-8", newline="\n",
    )
    return total


def write_wrangler_config(directory, database_id):
    (directory / "wrangler.json").write_bytes(json_bytes({
        "name": WORKER_NAME,
        "account_id": ACCOUNT_ID,
        "main": "worker.js",
        "compatibility_date": "2026-11-19",
        "workers_dev": True,
        "preview_urls": False,
        "assets": {"directory": "cloudflare-assets", "html_handling": "none"},
        "d1_databases": [{
            "binding": "ATTRIBUTES", "database_name": DATABASE_NAME, "database_id": database_id,
        }],
    }))


def package_frontend(directory, api_origin):
    origin = urlsplit(api_origin)
    if origin.scheme != "https" or origin.netloc != origin.hostname or origin.path not in ("", "/") or origin.query or origin.fragment:
        raise ValueError("API origin must be an HTTPS origin without a path")
    api_origin = f"https://{origin.netloc}"
    static = ROOT / "static"
    vendor = ROOT / "node_modules" / "maplibre-gl"
    assets = {
        "assets/app.js": (static / "app.js").read_bytes(),
        "assets/app.css": (static / "app.css").read_bytes(),
        "assets/logo.png": (static / "logo.png").read_bytes(),
        "assets/pmtiles-client.mjs": (directory / "pmtiles-client.mjs").read_bytes(),
        "maplibre/LICENSE.txt": (vendor / "LICENSE.txt").read_bytes(),
    }
    for name in ("maplibre-gl.css", "maplibre-gl.mjs", "maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"):
        assets[f"maplibre/{name}"] = (vendor / "dist" / name).read_bytes()
    index = (static / "index.html").read_text(encoding="utf-8")
    version = sha256(index.encode("utf-8") + api_origin.encode("ascii") + b"".join(assets.values())).hexdigest()[:12]
    prefix = f"/webgis-{version}"
    index = index.replace('name="webgis-api-origin" content=""', f'name="webgis-api-origin" content="{api_origin}"')
    index = index.replace('"/maplibre/', f'"{prefix}/maplibre/').replace('"/assets/', f'"{prefix}/assets/')
    assets["assets/app.js"] = assets["assets/app.js"].replace(b'"/maplibre/', f'"{prefix}/maplibre/'.encode("ascii"))
    assets[".htaccess"] = b"AddType text/javascript .mjs\n"
    assets["index.html"] = index.encode("utf-8")
    with ZipFile(directory / "frontend-assets.zip", "w", compression=ZIP_DEFLATED) as package:
        for path, content in assets.items():
            package.writestr(f"{prefix[1:]}/{path}", content)
    (directory / "index.html").write_text(index, encoding="utf-8")
    print(f"Frontend preview: {prefix}/, backend: {api_origin}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmtiles", type=Path, help="path to the Protomaps pmtiles executable")
    parser.add_argument("--api-origin", help="HTTPS origin for the deployed Worker")
    parser.add_argument("--database-id", help="ID of the project's Cloudflare D1 database")
    parser.add_argument("--frontend-only", action="store_true", help="rebuild frontend packaging only")
    args = parser.parse_args()
    if (args.frontend_only and not (args.api_origin or args.database_id)) or (not args.frontend_only and not args.pmtiles):
        parser.error("use --pmtiles to prepare the data, or --frontend-only with --api-origin or --database-id")

    catalog = public_catalog(json.loads((RUNTIME / "catalog.json").read_bytes()))
    version = catalog["version"]
    source = RUNTIME / version
    directory = RUNTIME / "deployment" / version
    if not args.frontend_only:
        chunks = split_tiles(catalog, source, directory, args.pmtiles.resolve())
        keys, count = export_attributes(source / "attributes.sqlite", directory, version)
        worker_data = {"catalog": catalog, "searchIndex": keys, "blockSize": BLOCK_SIZE}
        (directory / "cloudflare-worker-data.json").write_bytes(json_bytes(worker_data))
        print(f"Backend version {version}: {count} feature records; {chunks} static map chunks")
    if args.database_id:
        write_wrangler_config(directory, args.database_id)
    if args.api_origin:
        directory.mkdir(parents=True, exist_ok=True)
        package_frontend(directory, args.api_origin)


if __name__ == "__main__":
    main()
