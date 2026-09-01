"""
fetch_inegi.py — Fetch INEGI CEM 3.0 DEM data for Mexico via OGC WCS.

INEGI's Continuo de Elevaciones Mexicano (CEM 3.0) provides 15 m resolution
coverage across all of Mexico, significantly better than Copernicus GLO-30.
It is accessed via an OGC Web Coverage Service (WCS) endpoint.

--- Endpoint verification ---
INEGI's OGC service URLs change periodically. Before running this module,
confirm the active WCS endpoint by:
  1. Opening https://www.inegi.org.mx/app/geo2/elevacionesmex/ in a browser.
  2. Opening DevTools → Network tab → filtering for "wcs" or "cem".
  3. Copying the base URL from the GetCapabilities or GetCoverage request.
  4. Updating WCS_ENDPOINT below.

The endpoint and coverage ID used here reflect the most recently documented
public INEGI WCS service. Run discover_coverages() to probe the live service
and confirm the correct coverage identifier.
"""

import io
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.io import MemoryFile

try:
    from owslib.wcs import WebCoverageService
    from owslib.util import ServiceException
except ImportError:
    raise ImportError("owslib is required: pip install owslib")

# -----------------------------------------------------------------
# INEGI WCS configuration — update if the endpoint changes.
# -----------------------------------------------------------------
WCS_ENDPOINT = "https://gaia.inegi.org.mx/wcs/cem3/"
WCS_VERSION = "1.0.0"
COVERAGE_ID = "cem3"        # Verify via discover_coverages() if in doubt.
OUTPUT_FORMAT = "GeoTIFF"   # Or "image/tiff" depending on WCS version.
OUTPUT_CRS = "EPSG:4326"

# Resolution in decimal degrees: 0.000138889° ≈ 15 m at the equator.
DEFAULT_RESX = 0.000138889
DEFAULT_RESY = 0.000138889


def discover_coverages(endpoint: str = WCS_ENDPOINT, version: str = WCS_VERSION) -> list:
    """
    Probe the WCS endpoint and return a list of available coverage IDs.

    Useful for verifying the endpoint and finding the correct coverage name
    after an INEGI service update.
    """
    print(f"[INEGI] Querying GetCapabilities: {endpoint}")
    try:
        wcs = WebCoverageService(endpoint, version=version, timeout=30)
        coverages = list(wcs.contents.keys())
        print(f"[INEGI] Available coverages: {coverages}")
        return coverages
    except Exception as exc:
        raise RuntimeError(
            f"Could not reach INEGI WCS at {endpoint!r}.\n"
            "See module docstring for instructions on finding the current endpoint."
        ) from exc


def fetch(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    resolution_m: int = 15,
    output_path: str = "dem_inegi.tif",
    endpoint: str = WCS_ENDPOINT,
    coverage_id: str = COVERAGE_ID,
) -> str:
    """
    Fetch INEGI CEM DEM for a bounding box and save to a GeoTIFF.

    Parameters
    ----------
    min_lon, min_lat, max_lon, max_lat : float
        Bounding box in WGS84 decimal degrees. Must fall within Mexico.
    resolution_m : int
        Target resolution in metres. CEM 3.0 native is 15 m; 5 m and 1.5 m
        LiDAR products exist for some areas but use a separate coverage ID.
    output_path : str
        Destination GeoTIFF path.
    endpoint : str
        WCS service URL. Override if the default endpoint has changed.
    coverage_id : str
        WCS coverage identifier. Override if discover_coverages() shows a
        different name on the live service.

    Returns
    -------
    str
        Path to the saved GeoTIFF.
    """
    # Degrees per pixel at the requested resolution (~111,320 m per degree).
    resx = resolution_m / 111_320
    resy = resolution_m / 111_320

    print(f"[INEGI] AOI: {min_lon:.4f},{min_lat:.4f} → {max_lon:.4f},{max_lat:.4f}")
    print(f"[INEGI] Resolution: {resolution_m} m  |  Coverage: {coverage_id}")
    print(f"[INEGI] Endpoint: {endpoint}")

    try:
        wcs = WebCoverageService(endpoint, version=WCS_VERSION, timeout=60)
    except Exception as exc:
        raise RuntimeError(
            f"Could not connect to INEGI WCS at {endpoint!r}.\n"
            "Run discover_coverages() or check the module docstring."
        ) from exc

    if coverage_id not in wcs.contents:
        available = list(wcs.contents.keys())
        raise ValueError(
            f"Coverage {coverage_id!r} not found. Available: {available}\n"
            "Update COVERAGE_ID or pass coverage_id= explicitly."
        )

    print(f"[INEGI] Requesting coverage...")
    try:
        response = wcs.getCoverage(
            identifier=coverage_id,
            bbox=(min_lon, min_lat, max_lon, max_lat),
            crs=OUTPUT_CRS,
            resx=resx,
            resy=resy,
            format=OUTPUT_FORMAT,
        )
    except ServiceException as exc:
        raise RuntimeError(f"WCS GetCoverage failed: {exc}") from exc

    raw = response.read()
    if not raw:
        raise RuntimeError("WCS returned an empty response. Check bbox and coverage ID.")

    # Write via MemoryFile so we can re-profile before saving.
    with MemoryFile(raw) as memfile:
        with memfile.open() as src:
            profile = src.profile.copy()
            data = src.read()

    profile.update(
        driver="GTiff",
        compress="lzw",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(data)

    nodata = profile.get("nodata")
    valid = data[data != nodata].ravel() if nodata is not None else data.ravel()
    print(f"[INEGI] Saved: {output_path}  ({data.shape[2]}×{data.shape[1]} px)")
    if valid.size:
        print(f"[INEGI] Elevation: {float(valid.min()):.1f} – {float(valid.max()):.1f} m")

    return output_path
