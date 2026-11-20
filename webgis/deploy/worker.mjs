import data from "webgis:release";

const { catalog, blockSize, searchIndex } = data;
const layerIds = catalog.layers.map((layer) => layer.id).sort();
const origin = "https://chuyendoiluadongthap.x10.mx";

function json(body, status = 200, cacheControl = "no-store") {
  return Response.json(body, { status, headers: {
    "Access-Control-Allow-Origin": origin,
    "Cache-Control": cacheControl,
    "X-Content-Type-Options": "nosniff",
  } });
}

function notFound() {
  return json({ detail: "Không tìm thấy dữ liệu." }, 404);
}

async function readFeatures(database, matches) {
  if (matches.length === 0) return [];
  const needed = new Map();
  for (const { layer, fid } of matches) {
    if (!needed.has(layer)) needed.set(layer, new Set());
    needed.get(layer).add(Math.floor(fid / blockSize));
  }
  const groups = [...needed];
  const queries = groups.map(([layer, blocks]) => {
    const placeholders = Array.from(blocks, () => "?").join(",");
    return database.prepare(`SELECT block,records FROM feature_blocks
      WHERE version = ? AND layer = ? AND block IN (${placeholders})`).bind(catalog.version, layer, ...blocks);
  });
  const results = await database.batch(queries);
  const lookup = new Map(results.map(({ results: rows }, index) => [groups[index][0],
    new Map(rows.map(({ block, records }) => [block, JSON.parse(records)])),
  ]));
  const found = [];
  for (const { layer, fid } of matches) {
    const record = lookup.get(layer)?.get(Math.floor(fid / blockSize))?.[fid];
    if (record) {
      const [label, properties, bounds] = record;
      found.push({ layer, fid, label, properties, bounds });
    }
  }
  return found;
}

function normalize(value) {
  return value.toLowerCase().replaceAll("đ", "d").normalize("NFD").replace(/\p{M}/gu, "").trim().replace(/\s+/g, " ");
}

function compareGroups(a, b) {
  return (a.layer !== "ranh-xa") - (b.layer !== "ranh-xa") ||
    a.exact - b.exact || a.length - b.length || (a.layer < b.layer ? -1 : Number(a.layer > b.layer));
}

function rankMatches(query, selectedLayers, limit) {
  const groups = [];
  for (const layer of selectedLayers) {
    for (const [text, ids] of searchIndex[layer] ?? []) {
      if (text.includes(query)) groups.push({ layer, ids, exact: Number(text !== query), length: text.length });
    }
  }
  groups.sort(compareGroups);
  const matches = [];
  for (let index = 0; index < groups.length && matches.length < limit;) {
    const group = groups[index];
    const ids = [];
    do {
      ids.push(...groups[index].ids);
      index++;
    } while (index < groups.length && compareGroups(group, groups[index]) === 0);
    ids.sort((a, b) => a - b);
    for (const fid of ids.slice(0, limit - matches.length)) matches.push({ layer: group.layer, fid });
  }
  return matches;
}

async function search(database, query, layer, limit) {
  const normalized = normalize(query);
  const selectedLayers = layer ? [layer] : layerIds;
  let matches;
  if (/^#[0-9]{1,15}$/.test(normalized)) {
    matches = selectedLayers.map((name) => ({ layer: name, fid: Number(normalized.slice(1)) }));
  } else {
    if (normalized.length < 3) return [];
    matches = rankMatches(normalized, selectedLayers, limit);
  }
  const records = await readFeatures(database, matches);
  return records.slice(0, limit).map(({ layer, fid, label, bounds }) => ({ layer, fid, label, bounds }));
}

export default {
  async fetch(request, env) {
    const { pathname, searchParams } = new URL(request.url);
    if (request.method !== "GET") return json({ detail: "Chỉ hỗ trợ GET." }, 405);
    if (pathname === "/api/layers") return json(catalog, 200, "public, max-age=60");
    const prefix = `/api/${catalog.version}/`;
    if (!pathname.startsWith(prefix)) return notFound();
    const route = pathname.slice(prefix.length);
    try {
      const feature = /^features\/([a-z0-9-]+)\/(\d{1,15})$/.exec(route);
      if (feature && layerIds.includes(feature[1])) {
        const [result] = await readFeatures(env.ATTRIBUTES, [{ layer: feature[1], fid: Number(feature[2]) }]);
        return result ? json(result, 200, "public, max-age=86400, immutable") : notFound();
      }
      if (route === "search") {
        const query = searchParams.get("q") ?? "";
        const layer = searchParams.get("layer");
        const limit = Number(searchParams.get("limit") ?? "12");
        if (layer !== null && !layerIds.includes(layer)) return notFound();
        if (query.length < 2 || query.length > 100 || !Number.isInteger(limit) || limit < 1 || limit > 30) {
          return json({ detail: "Tham số tìm kiếm không hợp lệ." }, 422);
        }
        return json(await search(env.ATTRIBUTES, query, layer, limit));
      }
      return notFound();
    } catch (error) {
      console.error(error);
      return json({ detail: "Dịch vụ tra cứu tạm thời không đọc được dữ liệu." }, 503);
    }
  },
};
