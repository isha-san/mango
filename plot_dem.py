#!/usr/bin/env python3
"""
plot_dem.py — Visualize a DEM GeoTIFF as a colour topographic map.

Renders elevation using a terrain colormap with a hillshade overlay for a
realistic 3-D look. Saves to a PNG (or shows interactively if --output omitted).

Usage:
    python plot_dem.py data/sf_dem.tif
    python plot_dem.py data/sf_dem.tif --output figures/sf_topo.png
    python plot_dem.py data/sf_dem.tif --title "San Francisco — Copernicus GLO-30"
"""

import argparse
import sys
from pathlib import Path

from typing import Optional

import numpy as np
import rasterio
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.ticker import FuncFormatter


def hillshade(elevation: np.ndarray, azimuth: float = 315.0, altitude: float = 45.0) -> np.ndarray:
    """Compute a normalised [0, 1] hillshade from an elevation array."""
    az_rad = np.radians(360.0 - azimuth)
    alt_rad = np.radians(altitude)

    dy, dx = np.gradient(elevation)
    slope = np.arctan(np.sqrt(dx**2 + dy**2))
    aspect = np.arctan2(-dy, dx)

    shade = (
        np.sin(alt_rad) * np.cos(slope)
        + np.cos(alt_rad) * np.sin(slope) * np.cos(az_rad - aspect)
    )
    return np.clip(shade, 0, 1)


def terrain_colormap():
    """
    Custom terrain colormap:
      below 0 m  → deep blue (ocean / below sea level)
      0 – 50 m   → blue-green transition (intertidal / coastal)
      50 – 500 m → green → tan (lowland)
      500 m +    → brown → white (upland / peaks)
    """
    colors = [
        (-1.00, "#1a3a5c"),   # deep water
        (-0.02, "#4a90c4"),   # shallow water
        ( 0.00, "#a8d5a2"),   # sea level / coast
        ( 0.03, "#7ec87e"),   # lowland green
        ( 0.15, "#c8b560"),   # mid-elevation tan
        ( 0.40, "#a07040"),   # upland brown
        ( 0.70, "#806050"),   # high brown
        ( 1.00, "#f0f0f0"),   # peaks / snow
    ]
    positions = [c[0] for c in colors]
    # Normalise to [0, 1]
    lo, hi = positions[0], positions[-1]
    positions_norm = [(p - lo) / (hi - lo) for p in positions]
    hex_colors = [c[1] for c in colors]
    return mcolors.LinearSegmentedColormap.from_list(
        "mango_terrain", list(zip(positions_norm, hex_colors))
    )


def plot_dem(
    tif_path: str,
    output_path: Optional[str] = None,
    title: Optional[str] = None,
    hillshade_alpha: float = 0.4,
) -> None:
    with rasterio.open(tif_path) as src:
        elevation = src.read(1).astype(np.float32)
        nodata = src.nodata
        bounds = src.bounds
        crs = src.crs

    # Mask nodata
    if nodata is not None:
        elevation = np.where(elevation == nodata, np.nan, elevation)

    valid = elevation[~np.isnan(elevation)]
    elev_min, elev_max = float(valid.min()), float(valid.max())

    # Hillshade on the valid data (fill NaN with 0 for gradient stability)
    elev_filled = np.where(np.isnan(elevation), 0.0, elevation)
    shade = hillshade(elev_filled)

    cmap = terrain_colormap()
    norm = mcolors.Normalize(vmin=elev_min, vmax=elev_max)

    fig, ax = plt.subplots(figsize=(10, 8), dpi=150)

    # Extent in degrees for imshow axes labels
    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]

    # 1. Colour layer (elevation)
    im = ax.imshow(elevation, cmap=cmap, norm=norm, extent=extent, origin="upper")

    # 2. Hillshade overlay blended on top
    ax.imshow(
        shade,
        cmap="gray",
        alpha=hillshade_alpha,
        extent=extent,
        origin="upper",
        vmin=0,
        vmax=1,
    )

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Elevation (m)", fontsize=10)

    # Sea-level contour line
    if elev_min < 0 < elev_max:
        ax.contour(
            elev_filled,
            levels=[0],
            colors=["#003366"],
            linewidths=0.8,
            extent=extent,
            origin="upper",
        )

    # Labels
    ax.set_xlabel("Longitude (°)", fontsize=9)
    ax.set_ylabel("Latitude (°)", fontsize=9)
    ax.tick_params(labelsize=8)
    ax.grid(color="white", linewidth=0.3, alpha=0.5)

    plot_title = title or Path(tif_path).stem.replace("_", " ")
    ax.set_title(plot_title, fontsize=13, fontweight="bold", pad=10)

    fig.tight_layout()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"Saved → {output_path}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot a DEM GeoTIFF as a colour topographic map.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", help="Path to input DEM GeoTIFF.")
    parser.add_argument(
        "--output",
        default=None,
        help="Output PNG path. If omitted, display interactively.",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Map title. Defaults to the filename stem.",
    )
    parser.add_argument(
        "--hillshade-alpha",
        type=float,
        default=0.4,
        help="Opacity of the hillshade overlay (0 = off, 1 = full).",
    )

    args = parser.parse_args()
    plot_dem(
        tif_path=args.input,
        output_path=args.output,
        title=args.title,
        hillshade_alpha=args.hillshade_alpha,
    )


if __name__ == "__main__":
    main()
