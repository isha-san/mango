"""
fetch_dynamic_world.py — Fetch Dynamic World land cover data via Google Earth Engine.

Dynamic World (Google / WRI) is a near-real-time 10 m global land cover dataset
derived from Sentinel-2 imagery. Each pixel carries a discrete land cover label
plus per-class probability scores across 9 classes.

For mangrove migration analysis the most relevant classes are:
  flooded_vegetation — current mangrove / tidal wetland extent
  crops             — agricultural barrier to landward migration
  built             — urban/infrastructure barrier
  water             — open water / ocean

--- Authentication (one-time setup) ---
  python -c "import ee; ee.Authenticate()"

This opens a browser OAuth flow and saves credentials locally. Afterwards,
ee.Initialize() works without prompting. You will also need a Google Cloud
project with the Earth Engine API enabled; pass it via --project or the
GEE_PROJECT environment variable.
"""

import os
import sys
import io
import zipfile
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import requests
import rasterio
from rasterio.io import MemoryFile

try:
    import ee
except ImportError:
    raise ImportError("earthengine-api is required: pip install earthengine-api")


COLLECTION = "GOOGLE/DYNAMICWORLD/V1"

PROB_BANDS = [
    "water",
    "trees",
    "grass",
    "flooded_vegetation",
    "crops",
    "shrub_and_scrub",
    "built",
    "bare",
    "snow_and_ice",
]
ALL_BANDS = PROB_BANDS + ["label"]

# Integer label → class name mapping (matches band order above).
LABEL_NAMES = {i: name for i, name in enumerate(PROB_BANDS)}


def _initialize(project: str = None) -> None:
    """Initialize GEE, prompting for authentication if credentials are missing."""
    project = project or os.environ.get("GEE_PROJECT")
    try:
        ee.Initialize(project=project)
    except Exception:
        print("[DynamicWorld] Credentials not found — running ee.Authenticate()...")
        ee.Authenticate()
        ee.Initialize(project=project)


def _make_composite(
    collection: "ee.ImageCollection",
) -> "ee.Image":
    """
    Build a single composite image from a Dynamic World ImageCollection.

    Probability bands: mean across all scenes in the collection (float, 0–1).
    Label band:        mode (most frequent class across scenes, int 0–8).
    """
    prob_composite = collection.select(PROB_BANDS).mean()
    label_composite = (
        collection.select("label")
        .reduce(ee.Reducer.mode())
        .rename("label")
        .toInt()
    )
    return prob_composite.addBands(label_composite)


def fetch(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    start_date: str = None,
    end_date: str = None,
    scale: int = 10,
    output_path: str = "dynamic_world_aoi.tif",
    project: str = None,
) -> str:
    """
    Fetch a Dynamic World composite for a bounding box and save to a GeoTIFF.

    The output is a 10-band GeoTIFF:
      Bands 1–9 : mean class probabilities (float32, 0–1) in PROB_BANDS order.
      Band 10   : mode land cover label (int, 0–8).

    Parameters
    ----------
    min_lon, min_lat, max_lon, max_lat : float
        Bounding box in WGS84 decimal degrees.
    start_date, end_date : str
        ISO date strings (YYYY-MM-DD). Defaults to the previous 12 months.
        A longer window gives a more stable composite; shorter captures recent change.
    scale : int
        Output resolution in metres. DW native is 10 m. Increase for large AOIs
        to stay within the ~50 MB getDownloadURL size limit.
    output_path : str
        Destination GeoTIFF path.
    project : str
        Google Cloud project ID with Earth Engine API enabled. Falls back to
        the GEE_PROJECT environment variable.

    Returns
    -------
    str
        Path to the saved GeoTIFF.
    """
    if end_date is None:
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
    if start_date is None:
        start_date = (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d")

    _initialize(project)

    aoi = ee.Geometry.BBox(min_lon, min_lat, max_lon, max_lat)

    print(f"[DynamicWorld] AOI: {min_lon:.4f},{min_lat:.4f} → {max_lon:.4f},{max_lat:.4f}")
    print(f"[DynamicWorld] Date range: {start_date} → {end_date}  |  Scale: {scale} m")

    collection = (
        ee.ImageCollection(COLLECTION)
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
    )

    count = collection.size().getInfo()
    if count == 0:
        raise RuntimeError(
            f"No Dynamic World scenes found for the AOI between {start_date} and {end_date}. "
            "Try widening the date range."
        )
    print(f"[DynamicWorld] Scenes in collection: {count}")

    composite = _make_composite(collection)

    print("[DynamicWorld] Requesting download URL...")
    url = composite.getDownloadURL(
        {
            "name": "dynamic_world",
            "bands": ALL_BANDS,
            "region": aoi,
            "scale": scale,
            "crs": "EPSG:4326",
            "format": "ZIPPED_GEO_TIFF",
            "filePerBand": True,
        }
    )

    print("[DynamicWorld] Downloading...")
    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()

    # GEE returns a ZIP with one GeoTIFF per band; merge into a single raster.
    raw_zip = io.BytesIO(response.content)
    band_arrays = []
    profile = None

    with zipfile.ZipFile(raw_zip) as zf:
        # Sort filenames so band order matches ALL_BANDS.
        tif_names = sorted(n for n in zf.namelist() if n.endswith(".tif"))
        print(f"[DynamicWorld] Merging {len(tif_names)} band(s)...")

        for name in tif_names:
            with MemoryFile(zf.read(name)) as memfile:
                with memfile.open() as src:
                    if profile is None:
                        profile = src.profile.copy()
                    band_arrays.append(src.read(1))

    if not band_arrays:
        raise RuntimeError("Downloaded ZIP contained no GeoTIFF files.")

    mosaic = np.stack(band_arrays, axis=0)

    profile.update(
        count=mosaic.shape[0],
        driver="GTiff",
        compress="lzw",
        tiled=True,
        blockxsize=256,
        blockysize=256,
        dtype=mosaic.dtype,
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(mosaic)
        dst.update_tags(
            bands=",".join(ALL_BANDS),
            start_date=start_date,
            end_date=end_date,
            source=COLLECTION,
        )

    print(f"[DynamicWorld] Saved: {output_path}  ({mosaic.shape[2]}×{mosaic.shape[1]} px, {mosaic.shape[0]} bands)")
    return output_path
