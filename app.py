"""
app.py — Flask backend for the mango AOI viewer.

Serves a Leaflet map (templates/index.html) and a single JSON API that wraps
the existing fetch_*.py pipeline: pick a layer + AOI, fetch it (from cache if
we've already pulled that exact bbox), colorize rasters into a PNG, and hand
vector layers back as GeoJSON.

Run with:
    python app.py
Then open http://127.0.0.1:5000
"""

import base64
import hashlib
import traceback
from pathlib import Path

from flask import Flask, jsonify, render_template, request

import layers

app = Flask(__name__)

CACHE_DIR = Path(".webcache")
CACHE_DIR.mkdir(exist_ok=True)


def _cache_path(layer_id: str, bbox: tuple, ext: str) -> Path:
    key = f"{layer_id}:{','.join(f'{c:.4f}' for c in bbox)}"
    digest = hashlib.sha1(key.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{layer_id}_{digest}.{ext}"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/layers")
def api_layers():
    return jsonify({
        "layers": [
            {
                "id": layer_id,
                "label": cfg["label"],
                "category": cfg["category"],
                "kind": cfg["kind"],
                "coverage": cfg["coverage"],
            }
            for layer_id, cfg in layers.LAYERS.items()
        ],
        "category_defaults": layers.CATEGORY_DEFAULTS,
        "mexico_bbox": layers.MEXICO_BBOX,
    })


@app.route("/api/fetch")
def api_fetch():
    layer_id = request.args.get("layer_id")
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    radius_km = request.args.get("radius_km", type=float, default=15.0)

    if layer_id not in layers.LAYERS:
        return jsonify({"error": f"Unknown layer '{layer_id}'"}), 400
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon are required"}), 400

    cfg = layers.LAYERS[layer_id]
    bbox = layers.bbox_from_center(lon, lat, radius_km)

    if cfg["coverage"] and not layers._overlaps(bbox, cfg["coverage"]):
        return jsonify({"error": f"'{cfg['label']}' has no coverage at this location."}), 200

    cache_file = _cache_path(layer_id, bbox, cfg["ext"])
    try:
        if not cache_file.exists():
            cfg["fetch"](bbox, str(cache_file))
        result = cfg["render"](str(cache_file))
    except Exception as exc:  # noqa: BLE001 — surfaced to the UI as a debug aid
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 200

    if cfg["kind"] == "raster":
        return jsonify({
            "kind": "raster",
            "image": "data:image/png;base64," + base64.b64encode(result["png"]).decode(),
            "bounds": result["bounds"],
            "legend": result["legend"],
        })

    return jsonify({
        "kind": "vector",
        "geojson": result["geojson"],
    })


if __name__ == "__main__":
    app.run(debug=True, threaded=True)
