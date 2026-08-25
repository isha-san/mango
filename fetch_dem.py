#!/usr/bin/env python3
"""
fetch_dem.py — Fetch Copernicus GLO-30/GLO-90 DEM data for an area of interest.

Reads directly from public AWS S3 COGs via HTTP range requests — no full tile
download. Only the pixels covering the requested bounding box are transferred.

Usage examples:
    # 25 km buffer around a point in the Yucatan
    python fetch_dem.py --center -90.5 20.0 --buffer-km 25 --output yucatan.tif

    # Explicit bounding box, coarser 90 m resolution
    python fetch_dem.py --bbox -91.0 19.5 -90.0 20.5 --resolution 90 --output yucatan_90m.tif
"""

import argparse
import math
import os
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.merge import merge

# Tune GDAL for efficient COG range reads before any rasterio calls.
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("GDAL_HTTP_MULTIPLEX", "YES")
os.environ.setdefault("GDAL_HTTP_VERSION", "2")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")

# Copernicus DEM public S3 buckets (no credentials needed).
BUCKETS = {
    30: "copernicus-dem-30m",
    90: "copernicus-dem-90m",
}
# Pixel spacing in arc-seconds used in the tile filename.
ARC_SECONDS = {30: 10, 90: 30}


def tile_name(lat: int, lon: int, resolution: int) -> str:
    """Build the Copernicus DEM tile identifier for the 1°×1° cell at (lat, lon)."""
    lat_str = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}_00"
    lon_str = f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}_00"
    arcsec = ARC_SECONDS[resolution]
    return f"Copernicus_DSM_COG_{arcsec:02d}_{lat_str}_{lon_str}_DEM"


def tile_url(lat: int, lon: int, resolution: int) -> str:
    """Return the GDAL vsicurl URL for a single Copernicus DEM tile."""
    bucket = BUCKETS[resolution]
    name = tile_name(lat, lon, resolution)
    return f"/vsicurl/https://{bucket}.s3.amazonaws.com/{name}/{name}.tif"


def bbox_from_center(lon: float, lat: float, buffer_km: float) -> tuple:
    """Return (min_lon, min_lat, max_lon, max_lat) for a square centred at (lon, lat)."""
    d_lat = buffer_km / 111.32
    d_lon = buffer_km / (111.32 * math.cos(math.radians(lat)))
    return lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat


def tiles_for_bbox(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> list:
    """Return all (lat, lon) integer SW-corner pairs whose 1°×1° cell overlaps the bbox."""
    tiles = []
    for lat in range(math.floor(min_lat), math.ceil(max_lat)):
        for lon in range(math.floor(min_lon), math.ceil(max_lon)):
            tiles.append((lat, lon))
    return tiles


def fetch_dem(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    resolution: int,
    output_path: str,
) -> None:
    bbox = (min_lon, min_lat, max_lon, max_lat)
    tiles = tiles_for_bbox(*bbox)

    print(f"AOI bbox    : {min_lon:.4f}, {min_lat:.4f}  →  {max_lon:.4f}, {max_lat:.4f}")
    print(f"Resolution  : {resolution} m  (GLO-{resolution})")
    print(f"Tiles needed: {len(tiles)}")

    datasets = []
    for lat, lon in tiles:
        url = tile_url(lat, lon, resolution)
        print(f"  ↳ opening {url}")
        try:
            ds = rasterio.open(url)
            datasets.append(ds)
        except rasterio.errors.RasterioIOError as exc:
            print(f"    warning: skipping tile ({lat}, {lon}) — {exc}", file=sys.stderr)

    if not datasets:
        sys.exit("No tiles could be opened. Check coordinates and network access.")

    print("Merging tiles and clipping to AOI...")
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
    print(f"Saved       : {output_path}")
    print(f"Shape       : {mosaic.shape[2]} px wide × {mosaic.shape[1]} px tall")
    if valid.size:
        print(f"Elevation   : {valid.min():.1f} – {valid.max():.1f} m")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Copernicus DEM for an AOI via cloud-native COG range reads.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--center",
        nargs=2,
        metavar=("LON", "LAT"),
        type=float,
        help="Centre point in WGS84 decimal degrees (lon lat).",
    )
    source.add_argument(
        "--bbox",
        nargs=4,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        type=float,
        help="Bounding box in WGS84 decimal degrees.",
    )
    parser.add_argument(
        "--buffer-km",
        type=float,
        default=25.0,
        help="Half-width of square AOI in km (only with --center).",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        choices=[30, 90],
        default=30,
        help="DEM resolution in metres: 30 (GLO-30) or 90 (GLO-90).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="dem_aoi.tif",
        help="Output GeoTIFF path.",
    )

    args = parser.parse_args()

    if args.center:
        bbox = bbox_from_center(*args.center, args.buffer_km)
    else:
        bbox = tuple(args.bbox)

    fetch_dem(*bbox, resolution=args.resolution, output_path=args.output)


if __name__ == "__main__":
    main()
