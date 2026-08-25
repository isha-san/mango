# mango

Tools for building a mangrove landward-migration suitability model — identifying
restoration/conservation sites where mangroves can migrate inland ahead of
sea-level rise, rather than being squeezed out by it.

See `CLAUDE.md` for the full research background (why elevation and horizontal
migration matter, candidate data sources, and the target geographies).

## Status

Milestone 1: pull coastal DEM data into a pipeline for model development.
Currently implemented — fetch and visualize Copernicus GLO-30/GLO-90 elevation
data for an area of interest.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

**Fetch a DEM** for an area of interest (reads only the needed pixels via
cloud-native COG range requests — no full tile download):

```bash
# 25 km buffer around a point
python fetch_dem.py --center -90.5 20.0 --buffer-km 25 --output data/yucatan.tif

# Explicit bounding box, coarser 90 m resolution
python fetch_dem.py --bbox -91.0 19.5 -90.0 20.5 --resolution 90 --output data/yucatan_90m.tif
```

**Plot a DEM** as a colour topographic map with hillshade:

```bash
python plot_dem.py data/yucatan.tif --output figures/yucatan_topo.png --title "Yucatán — GLO-30"
```

Run either script with `--help` for the full flag list.

## Layout

| Path | Contents |
|---|---|
| `fetch_dem.py` | Downloads DEM tiles for an AOI from public Copernicus S3 buckets |
| `plot_dem.py` | Renders a DEM GeoTIFF as a shaded terrain map |
| `data/` | Fetched DEM GeoTIFFs |
| `figures/` | Rendered map PNGs |
