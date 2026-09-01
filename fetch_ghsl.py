"""
fetch_ghsl.py — Fetch Global Human Settlement Layer (GHSL) data from JRC.

GHSL is produced by the EU Joint Research Centre and provides multi-epoch
global data on built-up area, population, and degree of urbanisation.

For mangrove migration analysis the most relevant product is BUILT_S:
built-up surface area (m² of building footprint per cell), which directly
identifies urban and infrastructure barriers to landward migration.

Available products:
  built_s — Built-up surface area in m² per cell  (default)
  smod    — Degree of urbanisation (settlement model, categorical)
  pop     — Population count per cell

Resolution: 30 arc-seconds (~1 km at equator), global single-file ZIP.
Epochs: 1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025.

Access strategy:
  1. Try /vsizip/vsicurl/ — reads only the bytes covering the AOI from the
     remote ZIP via HTTP range requests. No download required if JRC's server
     supports range reads (it usually does).
  2. Fallback — download the full ZIP (~178 MB for BUILT_S 2020), extract,
     and cache the GeoTIFF locally at ~/.cache/mango/ghsl/. Subsequent calls
     reuse the cache so the download only happens once per product/epoch.
"""

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import requests
import rasterio
from rasterio.windows import from_bounds as window_from_bounds

# Tune GDAL for range reads from remote ZIPs.
import os
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("GDAL_HTTP_MULTIPLEX", "YES")
os.environ.setdefault("GDAL_HTTP_VERSION", "2")

BASE_FTP = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL"
RELEASE = "R2023A"
RESOLUTION = "30ss"   # 30 arc-seconds ≈ 1 km; global single file
VERSION = "V1-0"

PRODUCTS = {
    "built_s": {
        "dir":         "GHS_BUILT_S_GLOBE_R2023A",
        "prefix":      "GHS_BUILT_S",
        "description": "Built-up surface (m² of building footprint per cell)",
        "epochs":      [1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025],
    },
    "smod": {
        "dir":         "GHS_SMOD_GLOBE_R2023A",
        "prefix":      "GHS_SMOD",
        "description": "Degree of urbanisation (settlement model, categorical int)",
        "epochs":      [1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025],
    },
    "pop": {
        "dir":         "GHS_POP_GLOBE_R2023A",
        "prefix":      "GHS_POP",
        "description": "Population count per cell",
        "epochs":      [1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025],
    },
}

_CACHE_DIR = Path.home() / ".cache" / "mango" / "ghsl"


def _stem(product: str, epoch: int) -> str:
    prefix = PRODUCTS[product]["prefix"]
    return f"{prefix}_E{epoch}_GLOBE_{RELEASE}_4326_{RESOLUTION}_{VERSION.replace('-', '_')}"


def _zip_url(product: str, epoch: int) -> str:
    stem = _stem(product, epoch)
    d = PRODUCTS[product]["dir"]
    subdir = stem.replace(f"_{VERSION.replace('-', '_')}", "")
    return f"{BASE_FTP}/{d}/{subdir}/{VERSION}/{stem}.zip"


def _vsizip_url(product: str, epoch: int) -> str:
    """GDAL virtual path that reads directly from the remote ZIP via range requests."""
    zip_u = _zip_url(product, epoch)
    stem = _stem(product, epoch)
    return f"/vsizip//vsicurl/{zip_u}/{stem}.tif"


def _cached_tif(product: str, epoch: int) -> Path:
    return _CACHE_DIR / f"{_stem(product, epoch)}.tif"


def _download_and_cache(product: str, epoch: int) -> Path:
    """Download the global ZIP, extract the GeoTIFF, and cache it locally."""
    tif_path = _cached_tif(product, epoch)
    if tif_path.exists():
        print(f"[GHSL] Using cached file: {tif_path}")
        return tif_path

    url = _zip_url(product, epoch)
    print(f"[GHSL] Downloading {url} ...")
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    response = requests.get(url, stream=True, timeout=600)
    response.raise_for_status()

    total = int(response.headers.get("content-length", 0))
    received = 0
    chunks = []
    for chunk in response.iter_content(chunk_size=1 << 20):  # 1 MB chunks
        chunks.append(chunk)
        received += len(chunk)
        if total:
            pct = received / total * 100
            print(f"\r[GHSL] {received / 1e6:.0f} / {total / 1e6:.0f} MB  ({pct:.0f}%)", end="")
    print()

    raw = b"".join(chunks)
    stem = _stem(product, epoch)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        tif_name = next(n for n in zf.namelist() if n.endswith(".tif"))
        zf.extract(tif_name, _CACHE_DIR)
        extracted = _CACHE_DIR / tif_name
        if extracted != tif_path:
            extracted.rename(tif_path)

    print(f"[GHSL] Cached: {tif_path}  ({tif_path.stat().st_size / 1e6:.0f} MB)")
    return tif_path


def _open_dataset(product: str, epoch: int) -> rasterio.DatasetReader:
    """
    Open the GHSL GeoTIFF, preferring a remote vsizip read; downloading as fallback.
    """
    vsi_path = _vsizip_url(product, epoch)
    try:
        ds = rasterio.open(vsi_path)
        ds.read(1, window=rasterio.windows.Window(0, 0, 1, 1))  # probe range-read support
        print(f"[GHSL] Range reads supported — no download needed.")
        return ds
    except Exception:
        print("[GHSL] Range reads not available; falling back to local cache.")
        ds.close() if "ds" in dir() else None

    tif_path = _download_and_cache(product, epoch)
    return rasterio.open(tif_path)


def fetch(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    product: str = "built_s",
    epoch: int = 2020,
    output_path: str = "ghsl_aoi.tif",
) -> str:
    """
    Fetch a GHSL raster clipped to a bounding box and save to a GeoTIFF.

    Parameters
    ----------
    min_lon, min_lat, max_lon, max_lat : float
        Bounding box in WGS84 decimal degrees.
    product : str
        One of 'built_s', 'smod', 'pop'. Default: 'built_s'.
    epoch : int
        Data year. Available: 1975–2025 in 5-year steps. Default: 2020.
    output_path : str
        Destination GeoTIFF path.

    Returns
    -------
    str
        Path to the saved GeoTIFF.
    """
    if product not in PRODUCTS:
        raise ValueError(f"Unknown product {product!r}. Choose from: {list(PRODUCTS)}")
    if epoch not in PRODUCTS[product]["epochs"]:
        raise ValueError(f"Epoch {epoch} not available for {product!r}. "
                         f"Valid: {PRODUCTS[product]['epochs']}")

    print(f"[GHSL] Product: {product} — {PRODUCTS[product]['description']}")
    print(f"[GHSL] Epoch: {epoch}  |  AOI: {min_lon:.4f},{min_lat:.4f} → {max_lon:.4f},{max_lat:.4f}")

    with _open_dataset(product, epoch) as src:
        bbox = (min_lon, min_lat, max_lon, max_lat)
        window = window_from_bounds(*bbox, src.transform)
        data = src.read(window=window)
        transform = src.window_transform(window)
        profile = src.profile.copy()

    profile.update(
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        transform=transform,
        compress="lzw",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(data)
        dst.update_tags(product=product, epoch=str(epoch), source="JRC GHSL R2023A")

    nodata = profile.get("nodata")
    valid = data[data != nodata].ravel() if nodata is not None else data.ravel()
    print(f"[GHSL] Saved: {output_path}  ({data.shape[2]}×{data.shape[1]} px)")
    if valid.size:
        print(f"[GHSL] Value range: {valid.min():.1f} – {valid.max():.1f}")

    return output_path


def main() -> None:
    import argparse
    import math

    parser = argparse.ArgumentParser(
        description="Fetch GHSL data for an area of interest.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    aoi = parser.add_mutually_exclusive_group(required=True)
    aoi.add_argument("--center", nargs=2, metavar=("LON", "LAT"), type=float)
    aoi.add_argument("--bbox", nargs=4,
                     metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"), type=float)
    parser.add_argument("--buffer-km", type=float, default=25.0)
    parser.add_argument("--product", choices=list(PRODUCTS), default="built_s")
    parser.add_argument("--epoch", type=int, default=2020)
    parser.add_argument("--output", default="ghsl_aoi.tif")

    args = parser.parse_args()

    if args.center:
        lon, lat = args.center
        buf = args.buffer_km
        d_lat = buf / 111.32
        d_lon = buf / (111.32 * math.cos(math.radians(lat)))
        bbox = (lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat)
    else:
        bbox = tuple(args.bbox)

    fetch(*bbox, product=args.product, epoch=args.epoch, output_path=args.output)


if __name__ == "__main__":
    main()
