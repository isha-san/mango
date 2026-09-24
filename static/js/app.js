const ZOOM_THRESHOLD = 9;

const map = L.map("map").setView([20.0, -90.5], 6); // Yucatán, since that's where real data exists today

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
  maxZoom: 19,
}).addTo(map);

let meta = null;              // /api/layers response
let currentAOI = null;        // {lat, lon}
let aoiCircle = null;
const overlays = {};          // layer_id -> leaflet layer
const legends = {};           // layer_id -> legend object (or null)
const statusDots = {};        // layer_id -> DOM element

const BARRIER_STYLES = {
  seawall: { color: "#d64545", weight: 3 },
  embankment: { color: "#d64545", weight: 3 },
  dike: { color: "#d64545", weight: 3 },
  levee: { color: "#d64545", weight: 3 },
  aquaculture: { color: "#e0a800", weight: 1, fillOpacity: 0.3 },
  default: { color: "#888", weight: 1, dashArray: "3,3" },
};

function barrierStyle(feature) {
  const t = feature.properties.barrier_type || "";
  if (t.startsWith("road:")) return BARRIER_STYLES.default;
  return BARRIER_STYLES[t] || BARRIER_STYLES.default;
}

function radiusKm() {
  return parseFloat(document.getElementById("radius-input").value) || 15;
}

function showZoomToast() {
  let toast = document.getElementById("zoom-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "zoom-toast";
    toast.className = "zoom-toast";
    toast.textContent = "Zoom in further to select an AOI";
    document.body.appendChild(toast);
  }
  toast.style.display = "block";
  clearTimeout(showZoomToast._t);
  showZoomToast._t = setTimeout(() => (toast.style.display = "none"), 1500);
}

// ---------------------------------------------------------------------------
// Panel construction
// ---------------------------------------------------------------------------

function buildPanel() {
  const container = document.getElementById("layer-list");
  const byCategory = {};
  for (const layer of meta.layers) {
    (byCategory[layer.category] = byCategory[layer.category] || []).push(layer);
  }

  for (const [category, layerList] of Object.entries(byCategory)) {
    const box = document.createElement("div");
    box.className = "category";

    const title = document.createElement("div");
    title.className = "category-title";
    title.textContent = category;
    box.appendChild(title);

    const row = document.createElement("div");
    row.className = "layer-row";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.dataset.category = category;

    const label = document.createElement("label");

    let select = null;
    if (layerList.length > 1) {
      select = document.createElement("select");
      for (const layer of layerList) {
        const opt = document.createElement("option");
        opt.value = layer.id;
        opt.textContent = layer.label.split("—")[1]?.trim() || layer.label;
        select.appendChild(opt);
      }
      label.textContent = category;
      checkbox.addEventListener("change", () => onToggle(select.value, checkbox.checked));
      select.addEventListener("change", (e) => {
        const prev = select.dataset.active || layerList[0].id;
        if (checkbox.checked) onSourceSwap(prev, e.target.value);
        select.dataset.active = e.target.value;
      });
    } else {
      label.textContent = layerList[0].label;
      checkbox.addEventListener("change", () => onToggle(layerList[0].id, checkbox.checked));
    }

    const dot = document.createElement("span");
    dot.className = "status-dot";
    for (const layer of layerList) statusDots[layer.id] = dot;

    row.appendChild(checkbox);
    row.appendChild(label);
    if (select) row.appendChild(select);
    row.appendChild(dot);
    box.appendChild(row);
    container.appendChild(box);

    if (select) select.dataset.active = select.value;
  }
}

function activeLayerId(category) {
  const row = [...document.querySelectorAll(".category")].find(
    (c) => c.querySelector(".category-title").textContent === category
  );
  const select = row?.querySelector("select");
  const checkbox = row?.querySelector("input[type=checkbox]");
  if (!checkbox?.checked) return null;
  if (select) return select.value;
  return meta.layers.find((l) => l.category === category)?.id;
}

// ---------------------------------------------------------------------------
// Fetch + render
// ---------------------------------------------------------------------------

function setStatus(layerId, status, message) {
  const dot = statusDots[layerId];
  if (!dot) return;
  dot.className = "status-dot " + status;
  dot.title = message || "";
}

function clearOverlay(layerId) {
  if (overlays[layerId]) {
    map.removeLayer(overlays[layerId]);
    delete overlays[layerId];
  }
  legends[layerId] = null;
  renderLegend();
}

async function fetchLayer(layerId) {
  if (!currentAOI) return;
  setStatus(layerId, "loading");
  const url = `/api/fetch?layer_id=${layerId}&lat=${currentAOI.lat}&lon=${currentAOI.lon}&radius_km=${radiusKm()}`;

  let data;
  try {
    const res = await fetch(url);
    data = await res.json();
  } catch (err) {
    setStatus(layerId, "error", "Network error: " + err.message);
    return;
  }

  if (data.error) {
    setStatus(layerId, "error", data.error);
    clearOverlay(layerId);
    return;
  }

  clearOverlay(layerId);

  if (data.kind === "raster") {
    const bounds = data.bounds; // [[south, west], [north, east]]
    overlays[layerId] = L.imageOverlay(data.image, bounds, { opacity: 0.75 }).addTo(map);
    legends[layerId] = data.legend;
  } else if (data.kind === "vector") {
    overlays[layerId] = L.geoJSON(data.geojson, { style: barrierStyle }).addTo(map);
    legends[layerId] = {
      type: "barriers",
      label: "Infrastructure barriers",
    };
  }

  setStatus(layerId, "ok");
  renderLegend();
}

function onToggle(layerId, checked) {
  if (checked) {
    if (currentAOI) fetchLayer(layerId);
  } else {
    clearOverlay(layerId);
    setStatus(layerId, "");
  }
}

function onSourceSwap(prevId, nextId) {
  clearOverlay(prevId);
  setStatus(prevId, "");
  if (currentAOI) fetchLayer(nextId);
}

function refreshAllEnabled() {
  document.querySelectorAll(".category").forEach((box) => {
    const category = box.querySelector(".category-title").textContent;
    const id = activeLayerId(category);
    if (id) fetchLayer(id);
  });
}

// ---------------------------------------------------------------------------
// Legend rendering
// ---------------------------------------------------------------------------

function renderLegend() {
  const el = document.getElementById("legend");
  el.innerHTML = "";
  for (const legend of Object.values(legends)) {
    if (!legend) continue;
    const item = document.createElement("div");
    item.className = "legend-item";

    const label = document.createElement("div");
    label.className = "legend-label";
    label.textContent = legend.label;
    item.appendChild(label);

    if (legend.type === "continuous") {
      const bar = document.createElement("div");
      bar.className = "gradient-bar";
      bar.style.background = `linear-gradient(to right, ${legend.stops.join(",")})`;
      item.appendChild(bar);

      const labels = document.createElement("div");
      labels.className = "gradient-labels";
      labels.innerHTML = `<span>${legend.vmin}${legend.unit}</span><span>${legend.vmax}${legend.unit}</span>`;
      item.appendChild(labels);
    } else if (legend.type === "categorical") {
      for (const entry of legend.entries) {
        const swatchRow = document.createElement("div");
        swatchRow.className = "swatch-row";
        swatchRow.innerHTML = `<span class="swatch" style="background:${entry.color}"></span><span>${entry.name}</span>`;
        item.appendChild(swatchRow);
      }
    } else if (legend.type === "barriers") {
      const rows = [
        ["#d64545", "seawall / levee / dike / embankment"],
        ["#e0a800", "aquaculture pond"],
        ["#888", "road"],
      ];
      for (const [color, name] of rows) {
        const swatchRow = document.createElement("div");
        swatchRow.className = "swatch-row";
        swatchRow.innerHTML = `<span class="swatch" style="background:${color}"></span><span>${name}</span>`;
        item.appendChild(swatchRow);
      }
    }

    el.appendChild(item);
  }
}

// ---------------------------------------------------------------------------
// AOI selection
// ---------------------------------------------------------------------------

map.on("click", (e) => {
  if (map.getZoom() < ZOOM_THRESHOLD) {
    showZoomToast();
    return;
  }

  currentAOI = { lat: e.latlng.lat, lon: e.latlng.lng };

  if (aoiCircle) map.removeLayer(aoiCircle);
  aoiCircle = L.circle(e.latlng, {
    radius: radiusKm() * 1000,
    color: "#0f4d2e",
    weight: 1.5,
    fillOpacity: 0.05,
  }).addTo(map);

  // Auto-select elevation/land-cover source for this AOI (fetch_dem.py parity).
  const bbox = [
    currentAOI.lon - 0.01, currentAOI.lat - 0.01,
    currentAOI.lon + 0.01, currentAOI.lat + 0.01,
  ];
  const inMexico = overlapsBbox(bbox, meta.mexico_bbox);
  setSelectValue("elevation", inMexico ? "dem_inegi" : "dem_copernicus");

  refreshAllEnabled();
});

document.getElementById("radius-input").addEventListener("change", () => {
  if (!currentAOI) return;
  if (aoiCircle) aoiCircle.setRadius(radiusKm() * 1000);
  refreshAllEnabled();
});

function setSelectValue(category, value) {
  const row = [...document.querySelectorAll(".category")].find(
    (c) => c.querySelector(".category-title").textContent === category
  );
  const select = row?.querySelector("select");
  if (select) {
    select.value = value;
    select.dataset.active = value;
  }
}

function overlapsBbox(a, b) {
  return a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1];
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

async function boot() {
  const res = await fetch("/api/layers");
  meta = await res.json();
  buildPanel();

  const [minLon, minLat, maxLon, maxLat] = meta.mexico_bbox;
  L.rectangle(
    [[minLat, minLon], [maxLat, maxLon]],
    { color: "#0f4d2e", weight: 1, fillOpacity: 0.03, dashArray: "6,4", interactive: false }
  )
    .bindTooltip("INEGI DEM (5–15 m) only available inside this box — Copernicus (30 m) covers everywhere else",
      { sticky: true, className: "coverage-tooltip" })
    .addTo(map);
}

boot();
