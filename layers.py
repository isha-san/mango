"""
layers.py — Layer registry and raster colorization for the mango web viewer.

Each entry in LAYERS wraps one of the existing fetch_*.py scripts behind a
uniform interface: given a bbox, fetch the data to a temp file, then render
it into either a colorized PNG (raster) or pass through GeoJSON (vector).

This module intentionally does no fetching/rendering on import — it just
wires the registry together so app.py can dispatch by layer id.
"""

import io
import json
import math

import numpy as np
import rasterio

import fetch_copernicus
import fetch_inegi
import fetch_worldcover
import fetch_jrc_gsw
import fetch_ghsl
import fetch_osm_barriers
from plot_dem import terrain_colormap

from PIL import Image
import matplotlib.cm as cm
import matplotlib.colors as mcolors

# Approximate Mexico bbox — matches fetch_dem.py's auto-selection region, and
# doubles as the static "no data outside this box" mask for INEGI.
MEXICO_BBOX = (-118.4, 14.5, -86.7, 32.7)


def bbox_from_center(lon: float, lat: float, buffer_km: float) -> tuple:
    d_lat = buffer_km / 111.32
    d_lon = buffer_km / (111.32 * math.cos(math.radians(lat)))
    return lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat


def _overlaps(bbox_a, bbox_b) -> bool:
    a_min_lon, a_min_lat, a_max_lon, a_max_lat = bbox_a
    b_min_lon, b_min_lat, b_max_lon, b_max_lat = bbox_b
    return a_min_lon < b_max_lon and a_max_lon > b_min_lon and a_min_lat < b_max_lat and a_max_lat > b_min_lat


def aoi_overlaps_mexico(bbox) -> bool:
    return _overlaps(bbox, MEXICO_BBOX)


# ---------------------------------------------------------------------------
# Colour palettes
# ---------------------------------------------------------------------------

WORLDCOVER_COLORS = {
    10: "#006400",   # tree_cover
    20: "#FFBB22",   # shrubland
    30: "#FFFF4C",   # grassland
    40: "#F096FF",   # cropland
    50: "#FA0000",   # built_up
    60: "#B4B4B4",   # bare_sparse
    70: "#F0F0F0",   # snow_ice
    80: "#0064C8",   # water
    90: "#0096A0",   # herbaceous_wetland
    95: "#00CF75",   # mangroves
    100: "#FAE6A0",  # moss_lichen
}

DYNAMIC_WORLD_COLORS = {
    0: "#419BDF",  # water
    1: "#397D49",  # trees
    2: "#88B053",  # grass
    3: "#7A87C6",  # flooded_vegetation
    4: "#E49635",  # crops
    5: "#DFC35A",  # shrub_and_scrub
    6: "#C4281B",  # built
    7: "#A59B8F",  # bare
    8: "#B39FE1",  # snow_and_ice
}


def _lut_from_hex(color_map: dict, size: int) -> np.ndarray:
    """Build a (size, 4) uint8 lookup table from {int_value: '#rrggbb'}. Index 0 is transparent unless overridden."""
    lut = np.zeros((size, 4), dtype=np.uint8)
    for value, hex_color in color_map.items():
        rgb = mcolors.to_rgb(hex_color)
        lut[value] = (*(int(c * 255) for c in rgb), 255)
    return lut


def _png_bytes(rgba: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
    return buf.getvalue()


def _bounds_latlon(src) -> list:
    b = src.bounds
    return [[b.bottom, b.left], [b.top, b.right]]


def _continuous_legend(label: str, vmin: float, vmax: float, cmap_name: str, unit: str = "") -> dict:
    return {
        "type": "continuous",
        "label": label,
        "vmin": round(vmin, 2),
        "vmax": round(vmax, 2),
        "unit": unit,
        "cmap": cmap_name,
        "stops": [mcolors.to_hex(cm.get_cmap(cmap_name)(t)) for t in np.linspace(0, 1, 6)],
    }


def _categorical_legend(label: str, color_map: dict, names: dict) -> dict:
    return {
        "type": "categorical",
        "label": label,
        "entries": [
            {"value": v, "color": color_map[v], "name": names.get(v, str(v))}
            for v in sorted(color_map)
        ],
    }


# ---------------------------------------------------------------------------
# Renderers — each takes a GeoTIFF path, returns (png_bytes, bounds, legend)
# ---------------------------------------------------------------------------

def render_dem(path: str) -> dict:
    with rasterio.open(path) as src:
        elevation = src.read(1).astype(np.float32)
        nodata = src.nodata
        bounds = _bounds_latlon(src)

    mask = np.isnan(elevation) if nodata is None else (elevation == nodata)
    if nodata is not None:
        elevation = np.where(mask, np.nan, elevation)

    valid = elevation[~np.isnan(elevation)]
    if valid.size == 0:
        raise RuntimeError("DEM tile has no valid elevation pixels in this AOI.")
    vmin, vmax = float(np.percentile(valid, 1)), float(np.percentile(valid, 99))

    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    elev_filled = np.where(np.isnan(elevation), vmin, elevation)
    rgba = (terrain_colormap()(norm(elev_filled)) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(mask, 0, 255)

    return {
        "png": _png_bytes(rgba),
        "bounds": bounds,
        "legend": _continuous_legend("Elevation", vmin, vmax, "terrain", unit="m"),
    }


def render_worldcover(path: str) -> dict:
    with rasterio.open(path) as src:
        classes = src.read(1)
        bounds = _bounds_latlon(src)

    lut = _lut_from_hex(WORLDCOVER_COLORS, size=int(max(WORLDCOVER_COLORS)) + 1)
    safe = np.clip(classes, 0, lut.shape[0] - 1)
    rgba = lut[safe]

    return {
        "png": _png_bytes(rgba),
        "bounds": bounds,
        "legend": _categorical_legend(
            "Land cover (WorldCover)", WORLDCOVER_COLORS, fetch_worldcover.CLASSES
        ),
    }


def render_dynamic_world(path: str) -> dict:
    with rasterio.open(path) as src:
        label = src.read(src.count)  # label is always the last band
        bounds = _bounds_latlon(src)

    lut = _lut_from_hex(DYNAMIC_WORLD_COLORS, size=int(max(DYNAMIC_WORLD_COLORS)) + 1)
    safe = np.clip(label, 0, lut.shape[0] - 1).astype(int)
    rgba = lut[safe]

    import fetch_dynamic_world as fdw
    return {
        "png": _png_bytes(rgba),
        "bounds": bounds,
        "legend": _categorical_legend(
            "Land cover (Dynamic World)", DYNAMIC_WORLD_COLORS, fdw.LABEL_NAMES
        ),
    }


def render_jrc_occurrence(path: str) -> dict:
    with rasterio.open(path) as src:
        occurrence = src.read(1).astype(np.float32)
        bounds = _bounds_latlon(src)

    cmap = cm.get_cmap("Blues")
    norm = mcolors.Normalize(vmin=0, vmax=100)
    rgba = (cmap(norm(occurrence)) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(occurrence <= 0, 0, 200)  # 0% occurrence → transparent

    return {
        "png": _png_bytes(rgba),
        "bounds": bounds,
        "legend": _continuous_legend("Surface water occurrence", 0, 100, "Blues", unit="%"),
    }


def render_ghsl_built(path: str) -> dict:
    with rasterio.open(path) as src:
        built = src.read(1).astype(np.float32)
        nodata = src.nodata
        bounds = _bounds_latlon(src)

    if nodata is not None:
        built = np.where(built == nodata, 0, built)
    built = np.clip(built, 0, None)

    vmax = float(np.percentile(built, 99)) or 1.0
    cmap = cm.get_cmap("Reds")
    norm = mcolors.Normalize(vmin=0, vmax=vmax)
    rgba = (cmap(norm(built)) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(built <= 0, 0, 200)

    return {
        "png": _png_bytes(rgba),
        "bounds": bounds,
        "legend": _continuous_legend("Built-up surface", 0, vmax, "Reds", unit="m² / cell"),
    }


def render_osm_barriers(path: str) -> dict:
    with open(path) as f:
        geojson = json.load(f)
    return {"geojson": geojson}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
# Each entry:
#   category  — groups mutually-exclusive alternate sources in the UI panel
#   kind      — "raster" or "vector"
#   coverage  — bbox restricting where this source has data, or None (global)
#   fetch     — callable(bbox, output_path) -> output_path
#   render    — callable(output_path) -> dict (raster) or {"geojson": ...} (vector)
#   ext       — output file extension for the temp fetch target

LAYERS = {
    "dem_copernicus": {
        "label": "Elevation — Copernicus GLO-30",
        "category": "elevation",
        "kind": "raster",
        "coverage": None,
        "ext": "tif",
        "fetch": lambda bbox, out: fetch_copernicus.fetch(*bbox, output_path=out),
        "render": render_dem,
    },
    "dem_inegi": {
        "label": "Elevation — INEGI CEM 3.0 (Mexico)",
        "category": "elevation",
        "kind": "raster",
        "coverage": MEXICO_BBOX,
        "ext": "tif",
        "fetch": lambda bbox, out: fetch_inegi.fetch(*bbox, output_path=out),
        "render": render_dem,
    },
    "landcover_worldcover": {
        "label": "Land cover — ESA WorldCover 10m",
        "category": "landcover",
        "kind": "raster",
        "coverage": None,
        "ext": "tif",
        "fetch": lambda bbox, out: fetch_worldcover.fetch(*bbox, output_path=out),
        "render": render_worldcover,
    },
    "landcover_dynamicworld": {
        "label": "Land cover — Dynamic World (GEE)",
        "category": "landcover",
        "kind": "raster",
        "coverage": None,
        "ext": "tif",
        "fetch": lambda bbox, out: __import__("fetch_dynamic_world").fetch(*bbox, output_path=out),
        "render": render_dynamic_world,
    },
    "water_jrc": {
        "label": "Surface water — JRC Global Surface Water",
        "category": "water",
        "kind": "raster",
        "coverage": None,
        "ext": "tif",
        "fetch": lambda bbox, out: fetch_jrc_gsw.fetch(*bbox, product="occurrence", output_path=out),
        "render": render_jrc_occurrence,
    },
    "settlement_ghsl": {
        "label": "Built-up area — GHSL",
        "category": "settlement",
        "kind": "raster",
        "coverage": None,
        "ext": "tif",
        "fetch": lambda bbox, out: fetch_ghsl.fetch(*bbox, product="built_s", epoch=2020, output_path=out),
        "render": render_ghsl_built,
    },
    "barriers_osm": {
        "label": "Infrastructure barriers — OpenStreetMap",
        "category": "barriers",
        "kind": "vector",
        "coverage": None,
        "ext": "geojson",
        "fetch": lambda bbox, out: fetch_osm_barriers.fetch(*bbox, output_path=out),
        "render": render_osm_barriers,
    },
}

# category -> default layer id (mirrors fetch_dem.py's plain default; Mexico
# override is applied at request time in app.py via aoi_overlaps_mexico()).
CATEGORY_DEFAULTS = {
    "elevation": "dem_copernicus",
    "landcover": "landcover_worldcover",
}
