"""
fetch_worldcover.py — Fetch ESA WorldCover 10 m land cover from AWS S3.

ESA WorldCover is a global 10 m land cover map derived from Sentinel-1 and
Sentinel-2. It is distributed as Cloud Optimized GeoTIFFs in 3°×3° tiles on
a public S3 bucket — the same cloud-native access pattern as Copernicus DEM.

Land cover classes (pixel integer values):
  10  Tree cover
  20  Shrubland
  30  Grassland
  40  Cropland                  ← barrier to landward migration
  50  Built-up                  ← barrier to landward migration
  60  Bare / sparse vegetation
  70  Snow and ice
  80  Permanent water bodies
  90  Herbaceous wetland        ← potential migration substrate
  95  Mangroves                 ← current mangrove extent
  100 Moss and lichen

Available years: 2020 (v100) and 2021 (v200).
"""

import math
import os
import sys
from pathlib import Path

import rasterio
from rasterio.merge import merge

os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("GDAL_HTTP_MULTIPLEX", "YES")
os.environ.setdefault("GDAL_HTTP_VERSION", "2")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")

BUCKET = "esa-worldcover.s3.eu-central-1.amazonaws.com"

VERSIONS = {
    2020: "v100",
    2021: "v200",
}

# Class values most relevant to mangrove migration scoring.
CLASSES = {
    10:  "tree_cover",
    20:  "shrubland",
    30:  "grassland",
    40:  "cropland",
    50:  "built_up",
    60:  "bare_sparse",
    70:  "snow_ice",
    80:  "water",
    90:  "herbaceous_wetland",
    95:  "mangroves",
    100: "moss_lichen",
}


def _tile_origin(lat: float, lon: float) -> tuple:
    """Return the SW corner (lat, lon) of the 3°×3° tile containing (lat, lon)."""
    return math.floor(lat / 3) * 3, math.floor(lon / 3) * 3


def _tile_label(tile_lat: int, tile_lon: int) -> str:
    lat_str = f"{'N' if tile_lat >= 0 else 'S'}{abs(tile_lat):02d}"
    lon_str = f"{'E' if tile_lon >= 0 else 'W'}{abs(tile_lon):03d}"
    return f"{lat_str}{lon_str}"


def _tile_url(tile_lat: int, tile_lon: int, year: int) -> str:
    version = VERSIONS[year]
    label = _tile_label(tile_lat, tile_lon)
    stem = f"ESA_WorldCover_10m_{year}_{version}_{label}_Map"
    return f"/vsicurl/https://{BUCKET}/{version}/{year}/map/{stem}.tif"


def _tiles_for_bbox(min_lon, min_lat, max_lon, max_lat):
    tiles = set()
    lat = math.floor(min_lat / 3) * 3
    while lat < max_lat:
        lon = math.floor(min_lon / 3) * 3
        while lon < max_lon:
            tiles.add((lat, lon))
            lon += 3
        lat += 3
    return sorted(tiles)


def fetch(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    year: int = 2021,
    output_path: str = "worldcover_aoi.tif",
) -> str:
    """
    Fetch ESA WorldCover land cover for a bounding box and save to a GeoTIFF.

    Parameters
    ----------
    min_lon, min_lat, max_lon, max_lat : float
        Bounding box in WGS84 decimal degrees.
    year : int
        2020 or 2021. 2021 (v200) is the more recent and recommended default.
    output_path : str
        Destination GeoTIFF path.

    Returns
    -------
    str
        Path to the saved GeoTIFF.
    """
    if year not in VERSIONS:
        raise ValueError(f"year must be 2020 or 2021, got {year}")

    bbox = (min_lon, min_lat, max_lon, max_lat)
    tiles = _tiles_for_bbox(*bbox)

    print(f"[WorldCover] AOI: {min_lon:.4f},{min_lat:.4f} → {max_lon:.4f},{max_lat:.4f}")
    print(f"[WorldCover] Year: {year}  |  Tiles: {len(tiles)}")

    datasets = []
    for tile_lat, tile_lon in tiles:
        url = _tile_url(tile_lat, tile_lon, year)
        print(f"  ↳ {url}")
        try:
            datasets.append(rasterio.open(url))
        except rasterio.errors.RasterioIOError as exc:
            print(f"    warning: skipping tile ({tile_lat},{tile_lon}) — {exc}", file=sys.stderr)

    if not datasets:
        raise RuntimeError("No WorldCover tiles could be opened. Check coordinates.")

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
        dst.update_tags(
            source="ESA WorldCover",
            year=str(year),
            version=VERSIONS[year],
            classes=str(CLASSES),
        )

    print(f"[WorldCover] Saved: {output_path}  ({mosaic.shape[2]}×{mosaic.shape[1]} px)")
    return output_path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch ESA WorldCover 10 m land cover for an AOI.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    aoi = parser.add_mutually_exclusive_group(required=True)
    aoi.add_argument("--center", nargs=2, metavar=("LON", "LAT"), type=float)
    aoi.add_argument("--bbox", nargs=4,
                     metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"), type=float)
    parser.add_argument("--buffer-km", type=float, default=25.0)
    parser.add_argument("--year", type=int, choices=[2020, 2021], default=2021)
    parser.add_argument("--output", default="worldcover_aoi.tif")

    args = parser.parse_args()

    if args.center:
        import math
        lon, lat = args.center
        buf = args.buffer_km
        d_lat = buf / 111.32
        d_lon = buf / (111.32 * math.cos(math.radians(lat)))
        bbox = (lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat)
    else:
        bbox = tuple(args.bbox)

    fetch(*bbox, year=args.year, output_path=args.output)


if __name__ == "__main__":
    main()
