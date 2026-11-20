import * as maplibregl from "/maplibre/maplibre-gl.mjs";

const byId = (id) => document.getElementById(id);
const apiOrigin = document.querySelector('meta[name="webgis-api-origin"]')?.content || location.origin;
const formatNumber = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 4 });
const formatArea = new Intl.NumberFormat("vi-VN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const formatMeasure = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });

const CONVERSION_LABELS = {
  HNK: "Đất trồng cây hằng năm khác",
  CLN: "Đất trồng cây lâu năm",
  NTS: "Đất nuôi trồng thủy sản",
  CNT: "Đất chăn nuôi tập trung",
  NKH: "Đất nông nghiệp khác",
};

const DEFAULT_OUTLINES = {
  "lua-kiem-ke": { color: "#6b8e00", width: 0.65, overview_width: 0.15 },
  "lua-thuc-te": { color: "#1b7a43", width: 0.75, overview_width: 0.15, dash: [3, 2] },
  "ranh-tinh": { color: "#244f66", width: 2.4, dash: [6, 2] },
};

const REFERENCE_LABELS = {
  "ranh-tinh": "Ranh tỉnh",
  "ranh-xa": "Ranh xã, phường",
};

const SELECTED_LINE_COLOR = "#0066ff";
const MEASURE_COLOR = "#0284c7";

const basemaps = {
  google: {
    type: "raster", tileSize: 256, maxzoom: 20,
    tiles: ["https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}"],
    attribution: "© Google Maps",
  },
  imagery: {
    type: "raster", tileSize: 256, maxzoom: 19,
    tiles: ["https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
    attribution: "Esri, Vantor, Earthstar Geographics, and the GIS User Community",
  },
};

let map;
let catalog;
let api;
let archiveUrls;
let provinceBounds;
let selection;
let detailBounds = null;
let detailRequest;
let searchRequest;
let coordinateMarker;
let measurementMode = null;
let measurementPoints = [];
const layers = new Map();
const compactScreen = window.matchMedia("(max-width: 760px)");
let currentPanel;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function currentOpacity() {
  return (100 - Number(byId("opacity").value)) / 100;
}

async function getJson(url, signal) {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function notice(message) {
  byId("notice").hidden = !message;
  byId("notice").textContent = message || "";
}

function setPanel(panel, focusSearch = false) {
  currentPanel = panel;
  byId("controls").hidden = !panel;
  byId("layers-panel").hidden = panel !== "layers";
  byId("search-form").hidden = panel !== "search";
  byId("controls-toggle").setAttribute("aria-expanded", String(panel === "layers"));
  byId("search-toggle").setAttribute("aria-expanded", String(panel === "search"));
  if (focusSearch && panel === "search") byId("query").focus();
}

function layerVisibility(layer, visible) {
  layer.checkbox.checked = visible;
  for (const id of layer.styles) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
  if (layer.legend) layer.legend.hidden = !visible;
  if (!visible && selection?.layer === layer.id) closeDetail();
}

function addDataLayers() {
  const fillOpacity = currentOpacity();
  for (const entry of catalog.layers) {
    const { id, minzoom, maxzoom, bounds, color, kind, categories } = entry;
    const outline = id === "lua-2030" ? null : entry.outline ?? DEFAULT_OUTLINES[id];
    const source = { source: id, "source-layer": "features" };
    const selected = ["boolean", ["feature-state", "selected"], false];
    const archiveUrl = archiveUrls?.get(id);
    const tileSource = archiveUrl
      ? { url: archiveUrl }
      : { tiles: [`${api}/tiles/${id}/{z}/{x}/{y}.pbf`] };
    map.addSource(id, { type: "vector", bounds, minzoom, maxzoom, promoteId: "feature_id", ...tileSource });
    const styles = [];

    if (kind === "polygon") {
      const fillId = `${id}-fill`;
      const fill = categories?.length
        ? ["match", ["get", "land_code"], ...categories.flatMap(({ code, color }) => [code, color]), "transparent"]
        : color;
      map.addLayer({
        id: fillId,
        type: "fill",
        ...source,
        paint: { "fill-color": fill, "fill-opacity": fillOpacity, "fill-antialias": true },
      });
      styles.push(fillId);
    }

    if (kind === "boundary" || kind === "line") {
      const casingId = `${id}-casing`;
      map.addLayer({
        id: casingId,
        type: "line",
        ...source,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": "#ffffff",
          "line-width": kind === "line" ? 4.2 : 3.6,
          "line-opacity": kind === "line" ? 0.85 : 0.9,
        },
      });
      styles.push(casingId);
    }

    const lineId = `${id}-line`;
    if (kind === "polygon" && outline) {
      const overviewWidth = outline.overview_width ?? 0.14;
      const detailWidth = Math.max(outline.width ?? 0.7, 0.65);
      const midWidth = Number(Math.min(overviewWidth * 1.6, detailWidth).toFixed(2));
      map.addLayer({
        id: lineId,
        type: "line",
        ...source,
        layout: { "line-join": "round" },
        paint: {
          "line-color": outline.color ?? color,
          "line-width": [
            "interpolate", ["linear"], ["zoom"],
            7, overviewWidth,
            10, midWidth,
            12, detailWidth,
            16, Number((detailWidth * 1.35).toFixed(2)),
          ],
          "line-opacity": [
            "interpolate", ["linear"], ["zoom"],
            7, 0.2,
            10, 0.45,
            12, 0.88,
          ],
          ...(outline.dash ? { "line-dasharray": outline.dash } : {}),
        },
      });
      styles.push(lineId);
    } else if (kind !== "polygon") {
      const baseWidth = outline?.width ?? (kind === "line" ? 2.2 : 1.7);
      map.addLayer({
        id: lineId,
        type: "line",
        ...source,
        layout: { "line-join": "round", ...(outline?.dash ? {} : { "line-cap": "round" }) },
        paint: {
          "line-color": outline?.color ?? color,
          "line-width": baseWidth,
          "line-opacity": 1,
          ...(outline?.dash ? { "line-dasharray": outline.dash } : {}),
        },
      });
      styles.push(lineId);
    }

    if (kind !== "line") {
      const haloId = `${id}-selected-halo`;
      map.addLayer({
        id: haloId,
        type: "line",
        ...source,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": "#ffffff",
          "line-width": 5.5,
          "line-opacity": ["case", selected, 0.92, 0],
        },
      });
      styles.push(haloId);

      const selectedId = `${id}-selected`;
      map.addLayer({
        id: selectedId,
        type: "line",
        ...source,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": SELECTED_LINE_COLOR,
          "line-width": 3.4,
          "line-opacity": ["case", selected, 1, 0],
        },
      });
      styles.push(selectedId);
    }

    const label = REFERENCE_LABELS[id] ?? entry.label;
    layers.set(id, { ...entry, label, outline, styles, pickStyle: kind === "polygon" ? styles[0] : lineId });
  }

  if (map.getLayer("ranh-tinh-casing")) map.moveLayer("ranh-tinh-casing");
  if (map.getLayer("ranh-tinh-line")) map.moveLayer("ranh-tinh-line");
}

function applySwatchOutline(swatch, outline) {
  if (!outline) {
    swatch.style.setProperty("--swatch-border-width", "0px");
    return;
  }
  swatch.style.setProperty("--swatch-border-color", outline.color);
  swatch.style.setProperty("--swatch-border-style", outline.dash ? "dashed" : "solid");
  swatch.style.setProperty("--swatch-border-width", "1.5px");
}

function drawLayerControls() {
  const container = byId("layer-list");
  const groups = new Map();
  for (const layer of layers.values()) {
    if (!groups.has(layer.group)) {
      const group = element("div", "", "layer-group");
      group.append(element("h3", layer.group));
      container.append(group);
      groups.set(layer.group, group);
    }
    const activeCategories = layer.categories?.filter(({ count }) => count > 0) ?? [];
    const row = element("label", "", "layer");
    row.title = layer.categories
      ? activeCategories.map(({ code }) => CONVERSION_LABELS[code] ?? code).join(" · ")
      : layer.description;
    const checkbox = element("input");
    checkbox.type = "checkbox";
    checkbox.addEventListener("change", () => layerVisibility(layer, checkbox.checked));

    const swatchClass = layer.kind === "polygon" ? "swatch" : layer.kind === "line" ? "swatch line" : "swatch boundary";
    const swatch = element("span", "", swatchClass);
    if (activeCategories.length) {
      const step = 100 / activeCategories.length;
      const stops = activeCategories.map(({ color }, idx) => `${color} ${(idx * step).toFixed(1)}% ${((idx + 1) * step).toFixed(1)}%`).join(", ");
      swatch.style.setProperty("--swatch", `linear-gradient(135deg, ${stops})`);
    } else {
      swatch.style.setProperty("--swatch", layer.color);
    }
    if (layer.kind === "polygon") applySwatchOutline(swatch, layer.outline);

    row.append(checkbox, swatch, element("span", layer.label));
    const group = groups.get(layer.group);
    group.append(row);

    if (activeCategories.length) {
      const legend = element("ul", "", "legend");
      legend.setAttribute("aria-label", "Chú giải chuyển đổi lúa");
      for (const { code, color } of activeCategories) {
        const item = element("li");
        const itemSwatch = element("span", "", "swatch");
        itemSwatch.style.setProperty("--swatch", color);
        applySwatchOutline(itemSwatch, layer.outline);
        const codeBadge = element("span", code, "legend-code");
        const label = CONVERSION_LABELS[code] || code;
        const nameNode = element("span", label, "legend-label");
        nameNode.title = label;
        item.append(itemSwatch, codeBadge, nameNode);
        legend.append(item);
      }
      group.append(legend);
      layer.legend = legend;
    }

    layer.checkbox = checkbox;
    layerVisibility(layer, layer.visible);
    if (layer.kind !== "line") {
      const option = element("option", layer.short);
      option.value = layer.id;
      byId("search-layer").append(option);
    }
  }
}

function setBasemap(id) {
  byId("basemap").value = id;
  if (map.getLayer("base")) {
    map.removeLayer("base");
    map.removeSource("base");
  }
  const source = basemaps[id];
  if (source) {
    map.addSource("base", source);
    map.addLayer({ id: "base", type: "raster", source: "base" }, "lua-2030-fill");
  }
}

function setSelected(current) {
  if (selection) map.removeFeatureState({ source: selection.layer, sourceLayer: "features", id: selection.fid });
  selection = current;
  if (current) {
    map.setFeatureState({ source: current.layer, sourceLayer: "features", id: current.fid }, { selected: true });
  }
}

function closeDetail() {
  detailRequest?.abort();
  detailBounds = null;
  byId("detail-zoom").hidden = true;
  byId("detail-badge").hidden = true;
  byId("detail").hidden = true;
  setSelected(undefined);
}

async function openDetail(result, choices = []) {
  detailRequest?.abort();
  const controller = new AbortController();
  detailRequest = controller;
  const layer = layers.get(result.layer);
  setSelected(result);
  if (compactScreen.matches || currentPanel === "search") setPanel(null);

  const panel = byId("detail");
  const title = byId("detail-title");
  const badge = byId("detail-badge");
  const zoomButton = byId("detail-zoom");
  const body = byId("detail-body");

  detailBounds = result.bounds ?? null;
  zoomButton.hidden = !detailBounds;
  badge.textContent = layer.short;
  badge.style.setProperty("--badge-color", layer.color);
  badge.hidden = false;

  title.textContent = layer.label;
  body.replaceChildren(element("p", "Đang lấy thuộc tính…"));

  const choicesPanel = byId("choices");
  choicesPanel.replaceChildren();
  choicesPanel.hidden = choices.length < 2;
  if (choices.length > 1) {
    choicesPanel.append(element("p", `Có ${choices.length} đối tượng hiển thị tại điểm chọn`));
    for (const choice of choices) {
      const button = element("button", `${layers.get(choice.layer).short} · #${choice.fid}`);
      button.type = "button";
      button.setAttribute("aria-pressed", String(choice.layer === result.layer && choice.fid === result.fid));
      button.addEventListener("click", () => openDetail(choice, choices));
      choicesPanel.append(button);
    }
  }

  panel.hidden = false;
  title.focus({ preventScroll: true });

  try {
    const data = await getJson(`${api}/features/${result.layer}/${result.fid}`, controller.signal);
    if (controller.signal.aborted) return;
    detailBounds = data.bounds ?? result.bounds ?? null;
    zoomButton.hidden = !detailBounds;

    const list = element("dl");
    const shortDetails = layer.kind === "polygon";
    const properties = shortDetails ? [
      { label: "ID", value: String(data.fid) },
      ...data.properties.map(({ label, value }) => ({
        label, value: typeof value === "number" && label.startsWith("Diện tích")
          ? `${formatArea.format(value)} ha` : value,
      })),
    ] : [
      { label: "ID trong nguồn", value: data.fid },
      ...data.properties,
      { label: "Tệp nguồn", value: layer.source },
      { label: "Hệ tọa độ nguồn", value: `EPSG:${layer.epsg}` },
    ];
    for (const { label, value } of properties) {
      const line = element("div");
      line.append(element("dt", label), element("dd", typeof value === "number" && label !== "ID trong nguồn"
        ? formatNumber.format(value) : String(value)));
      list.append(line);
    }
    body.replaceChildren(list);
    if (!shortDetails && !data.bounds) body.append(element("p", "Đối tượng này có thuộc tính nhưng không còn vùng hiển thị sau kiểm tra hình học."));
  } catch (error) {
    if (error.name !== "AbortError") body.replaceChildren(element("p", "Không lấy được thuộc tính. Hãy thử lại."));
  }
}

function identify(point) {
  const pickable = [...layers.values()].filter((layer) => layer.checkbox.checked && layer.kind !== "line");
  if (!pickable.length) return closeDetail();
  const found = map.queryRenderedFeatures(point, { layers: pickable.map((layer) => layer.pickStyle) });
  const unique = new Map();
  for (const feature of found) {
    const fid = feature.properties.feature_id;
    if (Number.isSafeInteger(fid)) unique.set(`${feature.source}/${fid}`, { layer: feature.source, fid });
  }
  const choices = [...unique.values()];
  const preferred = choices.find((choice) => layers.get(choice.layer).kind === "polygon") ?? choices[0];
  if (preferred) openDetail(preferred, choices);
  else closeDetail();
}

function parseCoordinate(value) {
  const match = value.match(/^(-?\d+(?:\.\d+)?)[\s,;]+(-?\d+(?:\.\d+)?)$/);
  if (!match) return null;
  const first = Number(match[1]);
  const second = Number(match[2]);
  const [lng, lat] = Math.abs(first) <= 90 ? [second, first] : [first, second];
  return Math.abs(lat) <= 85 && Math.abs(lng) <= 180 ? [lng, lat] : null;
}

function fit(bounds, maxZoom) {
  map.fitBounds(bounds, { padding: 48, maxZoom, duration: 420 });
}

function provincePadding() {
  return compactScreen.matches ? 36 : { left: currentPanel === "layers" ? 364 : 56, right: 118, top: 56, bottom: 48 };
}

async function search(event) {
  event.preventDefault();
  searchRequest?.abort();
  const value = byId("query").value.trim();
  const results = byId("results");
  const coordinate = parseCoordinate(value);
  if (coordinate) {
    closeDetail();
    coordinateMarker?.remove();
    coordinateMarker = new maplibregl.Marker({ color: "#14533e" }).setLngLat(coordinate).addTo(map);
    map.flyTo({ center: coordinate, zoom: 15 });
    setPanel(null);
    results.hidden = true;
    return;
  }
  results.hidden = false;
  if (value.length < 3 && !/^#\d+$/.test(value)) {
    results.replaceChildren(element("p", "Nhập ít nhất 3 ký tự hoặc một cặp tọa độ."));
    return;
  }
  const controller = new AbortController();
  searchRequest = controller;
  results.replaceChildren(element("p", "Đang tìm…"));
  const params = new URLSearchParams({ q: value });
  if (byId("search-layer").value) params.set("layer", byId("search-layer").value);
  try {
    const matches = await getJson(`${api}/search?${params}`, controller.signal);
    if (controller.signal.aborted) return;
    results.replaceChildren();
    for (const match of matches) {
      const layer = layers.get(match.layer);
      const button = element("button", match.label || `Đối tượng #${match.fid}`);
      button.type = "button";
      button.append(element("small", `${layer.short} · #${match.fid}`));
      button.addEventListener("click", () => {
        coordinateMarker?.remove();
        layerVisibility(layer, true);
        if (match.bounds) fit(match.bounds, 17);
        openDetail(match);
      });
      results.append(button);
    }
    if (!matches.length) results.append(element("p", "Không tìm thấy kết quả trong dữ liệu hiện có."));
  } catch (error) {
    if (error.name !== "AbortError") results.replaceChildren(element("p", "Không truy cập được dịch vụ tìm kiếm."));
  }
}

function sphericalArea(points) {
  const radians = Math.PI / 180;
  const earthRadius = 6371008.8;
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const [lonA, latA] = points[i];
    const [lonB, latB] = points[(i + 1) % points.length];
    const delta = ((lonB - lonA + 540) % 360) - 180;
    sum += delta * radians * (Math.sin(latA * radians) + Math.sin(latB * radians));
  }
  return Math.abs(sum * earthRadius ** 2 / 2);
}

function refreshMeasurement(mode) {
  const points = measurementPoints;
  const haveArea = mode === "area" && points.length >= 3;
  const features = points.map((point) => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: point } }));
  if (points.length >= 2) {
    const geometry = haveArea
      ? { type: "Polygon", coordinates: [[...points, points[0]]] }
      : { type: "LineString", coordinates: points };
    features.unshift({ type: "Feature", properties: {}, geometry });
  }
  map.getSource("measure").setData({ type: "FeatureCollection", features });
  byId("measurement").hidden = !measurementMode && !points.length;
  byId("finish").disabled = !measurementMode || points.length < (mode === "area" ? 3 : 2);
  let label = mode === "area" ? "Chọn ít nhất 3 điểm trên bản đồ" : "Chọn ít nhất 2 điểm trên bản đồ";
  if (haveArea) {
    const area = sphericalArea(points);
    label = area >= 10_000 ? `≈ ${formatMeasure.format(area / 10_000)} ha` : `≈ ${formatMeasure.format(area)} m²`;
  } else if (mode === "length" && points.length >= 2) {
    const distance = points.slice(1).reduce((total, point, index) =>
      total + maplibregl.LngLat.convert(points[index]).distanceTo(maplibregl.LngLat.convert(point)), 0);
    label = distance >= 1_000 ? `≈ ${formatMeasure.format(distance / 1_000)} km` : `≈ ${formatMeasure.format(distance)} m`;
  }
  byId("measurement-text").textContent = label;
}

function setMeasurement(mode, clear) {
  const previous = measurementMode;
  measurementMode = mode;
  if (clear) measurementPoints = [];
  byId("measure-length").setAttribute("aria-pressed", String(mode === "length"));
  byId("measure-area").setAttribute("aria-pressed", String(mode === "area"));
  map.getCanvas().style.cursor = mode ? "crosshair" : "";
  refreshMeasurement(mode || previous);
}

function addMeasurementTools() {
  map.addSource("measure", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({
    id: "measure-area", source: "measure", type: "fill",
    filter: ["==", ["geometry-type"], "Polygon"],
    paint: { "fill-color": MEASURE_COLOR, "fill-opacity": 0.22 },
  });
  map.addLayer({
    id: "measure-outline-casing", source: "measure", type: "line",
    filter: ["!=", ["geometry-type"], "Point"],
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": "#ffffff", "line-width": 4.5, "line-opacity": 0.8 },
  });
  map.addLayer({
    id: "measure-outline", source: "measure", type: "line",
    filter: ["!=", ["geometry-type"], "Point"],
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": MEASURE_COLOR, "line-width": 2.5 },
  });
  map.addLayer({
    id: "measure-points", source: "measure", type: "circle",
    filter: ["==", ["geometry-type"], "Point"],
    paint: {
      "circle-radius": 4.5,
      "circle-color": MEASURE_COLOR,
      "circle-stroke-width": 2,
      "circle-stroke-color": "#ffffff",
    },
  });
  byId("measure-length").addEventListener("click", () => { closeDetail(); setMeasurement("length", true); });
  byId("measure-area").addEventListener("click", () => { closeDetail(); setMeasurement("area", true); });
  byId("clear").addEventListener("click", () => setMeasurement(null, true));
  byId("finish").addEventListener("click", () => setMeasurement(null, false));
}

async function init() {
  try {
    catalog = await getJson(`${apiOrigin}/api/layers`);
    api = `${apiOrigin}/api/${catalog.version}`;
    if (catalog.layers.some((layer) => layer.tileArchive)) {
      const { registerTileArchives } = await import("./pmtiles-client.mjs");
      archiveUrls = registerTileArchives(maplibregl, catalog.layers, apiOrigin);
    }
    const related = catalog.layers.filter((layer) => layer.kind === "polygon" || layer.id === "ranh-tinh");
    provinceBounds = [
      Math.min(...related.map((layer) => layer.bounds[0])),
      Math.min(...related.map((layer) => layer.bounds[1])),
      Math.max(...related.map((layer) => layer.bounds[2])),
      Math.max(...related.map((layer) => layer.bounds[3])),
    ];
    setPanel(compactScreen.matches ? null : "layers");
    map = new maplibregl.Map({
      container: "map", bounds: provinceBounds, fitBoundsOptions: { padding: provincePadding() },
      minZoom: Math.min(...related.map((layer) => layer.minzoom)),
      maxZoom: 22, renderWorldCopies: false, dragRotate: false, pitchWithRotate: false,
      style: { version: 8, sources: {}, layers: [
        { id: "background", type: "background", paint: { "background-color": "#eaf0ec" } },
      ] }, attributionControl: { compact: false },
    });
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: false } }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    map.on("error", (event) => {
      if (event.error?.url?.includes(`${api}/tiles/`) || event.error?.message?.startsWith("PMTiles ")) {
        notice("Không tải được một số ô chuyên đề. Hãy thử tải lại trang.");
      }
    });
    map.once("load", () => {
      try {
        addDataLayers();
        drawLayerControls();
        setBasemap("google");
        addMeasurementTools();
        notice("");
      } catch (error) {
        notice("Không khởi tạo được các lớp bản đồ.");
        console.error(error);
        return;
      }
      byId("controls-toggle").addEventListener("click", () => setPanel(currentPanel === "layers" ? null : "layers"));
      byId("search-toggle").addEventListener("click", () => setPanel(currentPanel === "search" ? null : "search", true));
      for (const button of document.querySelectorAll(".panel-close")) {
        button.addEventListener("click", () => {
          byId(currentPanel === "search" ? "search-toggle" : "controls-toggle").focus();
          setPanel(null);
        });
      }
      byId("basemap").addEventListener("change", (event) => setBasemap(event.target.value));
      byId("opacity").addEventListener("input", (event) => {
        const opacity = currentOpacity();
        byId("opacity-value").value = `${event.target.value}%`;
        for (const layer of layers.values()) {
          if (layer.kind === "polygon") map.setPaintProperty(layer.styles[0], "fill-opacity", opacity);
        }
      });
      byId("fit").addEventListener("click", () => map.fitBounds(provinceBounds, {
        padding: provincePadding(), maxZoom: 11, duration: 420,
      }));
      byId("search-form").addEventListener("submit", search);
      byId("detail-zoom").addEventListener("click", () => {
        if (detailBounds) fit(detailBounds, 17);
      });
      byId("detail-close").addEventListener("click", closeDetail);
      map.on("click", (event) => {
        if (measurementMode) {
          measurementPoints.push(event.lngLat.toArray());
          refreshMeasurement(measurementMode);
        } else {
          identify(event.point);
        }
      });
      const coordinates = (point) => {
        const lat = `${Math.abs(point.lat).toFixed(5)}° ${point.lat < 0 ? "S" : "N"}`;
        const lng = `${Math.abs(point.lng).toFixed(5)}° ${point.lng < 0 ? "W" : "E"}`;
        byId("coordinates").textContent = `${lat}  ${lng}`;
      };
      coordinates(map.getCenter());
      map.on("mousemove", (event) => coordinates(event.lngLat));
      map.on("moveend", () => coordinates(map.getCenter()));
    });
  } catch (error) {
    notice("Không mở được WebGIS. Kiểm tra máy chủ và hỗ trợ WebGL của trình duyệt.");
    console.error(error);
  }
}

init();
