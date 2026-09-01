#!/usr/bin/env python3
"""
fetch_dem.py — Orchestrator for DEM data fetching.

Selects the best available DEM source for the requested area of interest:
  - Mexico AOIs   → INEGI CEM 3.0 (15 m native), falls back to Copernicus on failure.
  - All other AOIs → Copernicus GLO-30/GLO-90 (30 m or 90 m) from AWS S3.

Usage examples:
    # Auto-select source (INEGI for Mexico, Copernicus elsewhere)
    python fetch_dem.py --center -90.5 20.0 --buffer-km 25 --output data/yucatan.tif

    # Force Copernicus even for Mexico
    python fetch_dem.py --center -99.1 19.4 --buffer-km 20 --source copernicus --output data/cdmx.tif

    # Explicit bounding box
    python fetch_dem.py --bbox -122.6 37.6 -122.2 37.95 --output data/sf.tif
"""

import argparse
import math
import sys

import fetch_copernicus
import fetch_inegi

# Approximate bounding box for Mexico (WGS84).
_MEXICO_BBOX = (-118.4, 14.5, -86.7, 32.7)


def bbox_from_center(lon: float, lat: float, buffer_km: float) -> tuple:
    """Return (min_lon, min_lat, max_lon, max_lat) for a square centred at (lon, lat)."""
    d_lat = buffer_km / 111.32
    d_lon = buffer_km / (111.32 * math.cos(math.radians(lat)))
    return lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat


def _overlaps_mexico(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> bool:
    mx_min_lon, mx_min_lat, mx_max_lon, mx_max_lat = _MEXICO_BBOX
    return (
        min_lon < mx_max_lon
        and max_lon > mx_min_lon
        and min_lat < mx_max_lat
        and max_lat > mx_min_lat
    )


def fetch(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    source: str = "auto",
    resolution: int = 30,
    output_path: str = "dem_aoi.tif",
) -> str:
    """
    Fetch the best available DEM for a bounding box and save to a GeoTIFF.

    Parameters
    ----------
    min_lon, min_lat, max_lon, max_lat : float
        Bounding box in WGS84 decimal degrees.
    source : str
        "auto"       — use INEGI for Mexico, Copernicus elsewhere.
        "copernicus" — always use Copernicus GLO-30/GLO-90.
        "inegi"      — always use INEGI CEM (Mexico only).
    resolution : int
        For Copernicus: 30 or 90 (metres). INEGI is always 15 m native.
    output_path : str
        Destination GeoTIFF path.

    Returns
    -------
    str
        Path to the saved GeoTIFF.
    """
    bbox = (min_lon, min_lat, max_lon, max_lat)

    use_inegi = source == "inegi" or (
        source == "auto" and _overlaps_mexico(*bbox)
    )

    if use_inegi:
        try:
            return fetch_inegi.fetch(*bbox, output_path=output_path)
        except Exception as exc:
            if source == "inegi":
                raise
            print(
                f"[orchestrator] INEGI fetch failed ({exc}). "
                "Falling back to Copernicus.",
                file=sys.stderr,
            )

    return fetch_copernicus.fetch(*bbox, resolution=resolution, output_path=output_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch the best available DEM for an area of interest.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    aoi = parser.add_mutually_exclusive_group(required=True)
    aoi.add_argument(
        "--center",
        nargs=2,
        metavar=("LON", "LAT"),
        type=float,
        help="Centre point in WGS84 decimal degrees (lon lat).",
    )
    aoi.add_argument(
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
        "--source",
        choices=["auto", "copernicus", "inegi"],
        default="auto",
        help=(
            "DEM source. 'auto' uses INEGI for Mexico, Copernicus elsewhere. "
            "INEGI falls back to Copernicus if the WCS endpoint is unreachable."
        ),
    )
    parser.add_argument(
        "--resolution",
        type=int,
        choices=[30, 90],
        default=30,
        help="Copernicus resolution in metres (ignored when using INEGI).",
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

    fetch(
        *bbox,
        source=args.source,
        resolution=args.resolution,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
