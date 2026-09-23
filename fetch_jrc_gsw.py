"""
fetch_jrc_gsw.py — Fetch JRC Global Surface Water data via COG range reads.

The JRC Global Surface Water dataset (Pekel et al. 2016) tracks the presence
of surface water at 30 m resolution globally from 1984 to 2024. It is
distributed as GeoTIFFs in 10°×10° tiles on a public CloudFerro object store.

For mangrove migration analysis, the most relevant products are:
  occurrence   — % of time a pixel was water (1984–2024). High values indicate
                 permanent water; low values tidal / seasonal. Key for mapping
                 hydrological connectivity of potential migration corridors.
  seasonality  — number of months per year a pixel was water (0–12). Identifies
                 tidal flats and seasonally flooded areas that mangroves can
                 colonise.
  extent       — maximum water extent ever observed (binary 0/1). Conservative
                 estimate of reachable tidal/aquatic zone.

Available products: occurrence, seasonality, recurrence, change, transitions, extent
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

BASE_URL = (
    "https://s3.waw4-1.cloudferro.com/swift/v1/global-surface-water"
    "/download2024/Aggregated/VER1-5"
)
VERSION_SUFFIX = "v1_5_2024"

PRODUCTS = {
    "occurrence":   "% of time water present (0–100)",
    "seasonality":  "months/year water present (0–12)",
    "recurrence":   "% of years water present in wet season (0–100)",
    "change":       "change in occurrence 1984–99 vs 2000–2024 (-100–100)",
    "transitions":  "categorical surface water change class (int)",
    "extent":       "maximum water extent ever observed (0=no water, 1=water, 2=land)",
}


def _tile_label(tile_lat: int, tile_lon: int) -> str:
    """Build the tile label for the 10°×10° cell with SW corner at (tile_lat, tile_lon)."""
    lon_str = f"{abs(tile_lon)}{'E' if tile_lon >= 0 else 'W'}"
    lat_str = f"{abs(tile_lat)}{'N' if tile_lat >= 0 else 'S'}"
    return f"{lon_str}_{lat_str}"


def _tile_url(tile_lat: int, tile_lon: int, product: str) -> str:
    label = _tile_label(tile_lat, tile_lon)
    filename = f"{product}_{label}_{VERSION_SUFFIX}.tif"
    return f"/vsicurl/{BASE_URL}/{product}/{filename}"


def _tiles_for_bbox(min_lon, min_lat, max_lon, max_lat):
    tiles = set()
    lat = math.floor(min_lat / 10) * 10
    while lat < max_lat:
        lon = math.floor(min_lon / 10) * 10
        while lon < max_lon:
            tiles.add((lat, lon))
            lon += 10
        lat += 10
    return sorted(tiles)


def fetch(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    product: str = "occurrence",
    output_path: str = "jrc_gsw_aoi.tif",
) -> str:
    """
    Fetch a JRC Global Surface Water layer clipped to a bounding box.

    Parameters
    ----------
    min_lon, min_lat, max_lon, max_lat : float
        Bounding box in WGS84 decimal degrees.
    product : str
        One of: occurrence, seasonality, recurrence, change, transitions, extent.
        Default: 'occurrence'.
    output_path : str
        Destination GeoTIFF path.

    Returns
    -------
    str
        Path to the saved GeoTIFF.
    """
    if product not in PRODUCTS:
        raise ValueError(f"Unknown product {product!r}. Choose from: {list(PRODUCTS)}")

    bbox = (min_lon, min_lat, max_lon, max_lat)
    tiles = _tiles_for_bbox(*bbox)

    print(f"[JRC GSW] Product: {product} — {PRODUCTS[product]}")
    print(f"[JRC GSW] AOI: {min_lon:.4f},{min_lat:.4f} → {max_lon:.4f},{max_lat:.4f}")
    print(f"[JRC GSW] Tiles: {len(tiles)}")

    datasets = []
    for tile_lat, tile_lon in tiles:
        url = _tile_url(tile_lat, tile_lon, product)
        print(f"  ↳ {url}")
        try:
            datasets.append(rasterio.open(url))
        except rasterio.errors.RasterioIOError as exc:
            print(f"    warning: skipping tile ({tile_lat},{tile_lon}) — {exc}", file=sys.stderr)

    if not datasets:
        raise RuntimeError(
            "No JRC GSW tiles could be opened. "
            "Check coordinates and that the AOI is not entirely ocean."
        )

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
            source="JRC Global Surface Water v1.5 (2024)",
            product=product,
            description=PRODUCTS[product],
        )

    nodata = profile.get("nodata")
    valid = mosaic[mosaic != nodata].ravel() if nodata is not None else mosaic.ravel()
    print(f"[JRC GSW] Saved: {output_path}  ({mosaic.shape[2]}×{mosaic.shape[1]} px)")
    if valid.size:
        print(f"[JRC GSW] Value range: {valid.min()} – {valid.max()}")

    return output_path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch JRC Global Surface Water data for an AOI.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    aoi = parser.add_mutually_exclusive_group(required=True)
    aoi.add_argument("--center", nargs=2, metavar=("LON", "LAT"), type=float)
    aoi.add_argument("--bbox", nargs=4,
                     metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"), type=float)
    parser.add_argument("--buffer-km", type=float, default=25.0)
    parser.add_argument("--product", choices=list(PRODUCTS), default="occurrence")
    parser.add_argument("--output", default="jrc_gsw_aoi.tif")

    args = parser.parse_args()

    if args.center:
        lon, lat = args.center
        buf = args.buffer_km
        d_lat = buf / 111.32
        d_lon = buf / (111.32 * math.cos(math.radians(lat)))
        bbox = (lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat)
    else:
        bbox = tuple(args.bbox)

    fetch(*bbox, product=args.product, output_path=args.output)


if __name__ == "__main__":
    main()
