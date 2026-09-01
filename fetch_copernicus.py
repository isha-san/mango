"""
fetch_copernicus.py — Fetch Copernicus GLO-30 / GLO-90 DEM tiles from AWS S3.

Tiles are Cloud Optimized GeoTIFFs stored in a public S3 bucket. GDAL's
/vsicurl/ driver issues HTTP range requests so only the bytes covering the
requested bounding box are transferred — no full tile downloads.

Public bucket, no AWS credentials required.
"""

import os
import sys
import math
from pathlib import Path

import rasterio
from rasterio.merge import merge

# Tune GDAL for efficient COG range reads before any rasterio calls.
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("GDAL_HTTP_MULTIPLEX", "YES")
os.environ.setdefault("GDAL_HTTP_VERSION", "2")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")

BUCKETS = {30: "copernicus-dem-30m", 90: "copernicus-dem-90m"}
# Pixel spacing in arc-seconds encoded in the Copernicus tile filename.
ARC_SECONDS = {30: 10, 90: 30}


def _tile_name(lat: int, lon: int, resolution: int) -> str:
    lat_str = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}_00"
    lon_str = f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}_00"
    return f"Copernicus_DSM_COG_{ARC_SECONDS[resolution]:02d}_{lat_str}_{lon_str}_DEM"


def _tile_url(lat: int, lon: int, resolution: int) -> str:
    bucket = BUCKETS[resolution]
    name = _tile_name(lat, lon, resolution)
    return f"/vsicurl/https://{bucket}.s3.amazonaws.com/{name}/{name}.tif"


def _tiles_for_bbox(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> list:
    """Return (lat, lon) SW-corner pairs for every 1°×1° tile overlapping the bbox."""
    return [
        (lat, lon)
        for lat in range(math.floor(min_lat), math.ceil(max_lat))
        for lon in range(math.floor(min_lon), math.ceil(max_lon))
    ]


def fetch(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    resolution: int = 30,
    output_path: str = "dem_copernicus.tif",
) -> str:
    """
    Fetch Copernicus DEM for a bounding box and save to a GeoTIFF.

    Parameters
    ----------
    min_lon, min_lat, max_lon, max_lat : float
        Bounding box in WGS84 decimal degrees.
    resolution : int
        30 for GLO-30 (~30 m/px) or 90 for GLO-90 (~90 m/px).
    output_path : str
        Destination GeoTIFF path.

    Returns
    -------
    str
        Path to the saved GeoTIFF.
    """
    if resolution not in (30, 90):
        raise ValueError(f"resolution must be 30 or 90, got {resolution}")

    bbox = (min_lon, min_lat, max_lon, max_lat)
    tiles = _tiles_for_bbox(*bbox)

    print(f"[Copernicus] AOI: {min_lon:.4f},{min_lat:.4f} → {max_lon:.4f},{max_lat:.4f}")
    print(f"[Copernicus] Resolution: {resolution} m  |  Tiles: {len(tiles)}")

    datasets = []
    for lat, lon in tiles:
        url = _tile_url(lat, lon, resolution)
        print(f"  ↳ {url}")
        try:
            datasets.append(rasterio.open(url))
        except rasterio.errors.RasterioIOError as exc:
            print(f"    warning: skipping tile ({lat},{lon}) — {exc}", file=sys.stderr)

    if not datasets:
        raise RuntimeError("No Copernicus tiles could be opened. Check coordinates and network.")

    mosaic, transform = merge(datasets, bounds=bbox)

    profile = datasets[0].profile.copy()
    profile.update(
        driver="GTiff",
        height=mosaic.shape[1],
        width=mosaic.shape[2],
        transform=transform,
        compress="lzw",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )
    for ds in datasets:
        ds.close()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(mosaic)

    nodata = profile.get("nodata")
    valid = mosaic[mosaic != nodata].ravel() if nodata is not None else mosaic.ravel()
    print(f"[Copernicus] Saved: {output_path}  ({mosaic.shape[2]}×{mosaic.shape[1]} px)")
    if valid.size:
        print(f"[Copernicus] Elevation: {valid.min():.1f} – {valid.max():.1f} m")

    return output_path
