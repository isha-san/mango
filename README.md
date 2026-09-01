# mango

Tools for building a mangrove landward-migration suitability model — identifying
restoration/conservation sites where mangroves can migrate inland ahead of
sea-level rise, rather than being squeezed out by it.

See `CLAUDE.md` for the full research background (why elevation and horizontal
migration matter, candidate data sources, and the target geographies).

## Status

Milestone 1 in progress: building a data pipeline for model development.

| Layer | Source | Status |
|---|---|---|
| Elevation (DEM) | Copernicus GLO-30/GLO-90 (AWS S3) | ✅ |
| Elevation (DEM, Mexico) | INEGI CEM 3.0 (WCS) | ✅ (endpoint needs verification) |
| Built-up area / urbanisation | GHSL R2023A (JRC) | ✅ |
| Land cover | Dynamic World | — (deferred) |
| Infrastructure barriers | OpenStreetMap, Global Dam Watch | — |

## Setup

```bash
pip install -r requirements.txt
```

**INEGI (Mexico DEM)** additionally requires verifying the WCS endpoint — see
the docstring in `fetch_inegi.py` for instructions.

## Usage

### Elevation data

`fetch_dem.py` is the main entry point. It auto-selects INEGI CEM for Mexico
AOIs and Copernicus GLO-30/GLO-90 everywhere else (with automatic fallback).

```bash
# Auto-select source (INEGI for Mexico, Copernicus elsewhere)
python fetch_dem.py --center -90.5 20.0 --buffer-km 25 --output data/yucatan.tif

# Explicit bounding box
python fetch_dem.py --bbox -91.0 19.5 -90.0 20.5 --output data/yucatan_bbox.tif

# Force Copernicus even for Mexico; coarser 90 m resolution
python fetch_dem.py --center -99.1 19.4 --buffer-km 20 --source copernicus --resolution 90 --output data/cdmx_90m.tif
```

The fetchers use cloud-native range requests (GDAL `/vsicurl/`) to read only
the pixels covering the AOI — no full tile downloads.

### Human settlement data

`fetch_ghsl.py` fetches Global Human Settlement Layer data (built-up area,
degree of urbanisation, or population) from the JRC public server.

```bash
# Built-up surface area, 2020 (default)
python fetch_ghsl.py --center -90.5 20.0 --buffer-km 25 --output data/yucatan_built.tif

# Degree of urbanisation, 2015
python fetch_ghsl.py --bbox -91.0 19.5 -90.0 20.5 --product smod --epoch 2015 --output data/yucatan_smod.tif

# Population count
python fetch_ghsl.py --center -90.5 20.0 --product pop --output data/yucatan_pop.tif
```

GHSL first tries HTTP range reads from the remote ZIP (no download needed).
If the server does not support range reads, it downloads the global file
(~178 MB) once and caches it at `~/.cache/mango/ghsl/`.

Available epochs: 1975–2025 in 5-year steps.

### Visualisation

```bash
python plot_dem.py data/yucatan.tif --output figures/yucatan_topo.png --title "Yucatán — GLO-30"
python plot_dem.py data/sf_dem.tif --output figures/sf_topo.png
```

Run any script with `--help` for the full flag list.

## Layout

| Path | Contents |
|---|---|
| `fetch_dem.py` | Orchestrator — selects DEM source, exposes CLI |
| `fetch_copernicus.py` | Copernicus GLO-30/GLO-90 from AWS S3 (COG range reads) |
| `fetch_inegi.py` | INEGI CEM 3.0 for Mexico via OGC WCS |
| `fetch_ghsl.py` | GHSL built-up, urbanisation, population from JRC |
| `plot_dem.py` | Renders a DEM GeoTIFF as a colour hillshade terrain map |
| `data/` | Fetched GeoTIFFs (not committed) |
| `figures/` | Rendered map PNGs |
