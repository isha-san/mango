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
| Land cover | ESA WorldCover 10 m (AWS S3) | ✅ |
| Surface water / hydrology | JRC Global Surface Water (CloudFerro) | ✅ |
| Infrastructure barriers (roads, levees, seawalls, aquaculture) | OpenStreetMap (Overpass API) | ✅ |
| Upstream dam/reservoir barriers | Global Dam Watch | TODO |

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

### Land cover

`fetch_worldcover.py` fetches ESA WorldCover 10 m land cover from AWS S3 (same
COG range-read pattern as Copernicus DEM — no full tile downloads). Includes a
dedicated mangrove class (95) alongside cropland (40) and built-up (50) which
are the primary barriers to landward migration.

```bash
python fetch_worldcover.py --center -90.5 20.0 --buffer-km 25 --output data/yucatan_lc.tif
python fetch_worldcover.py --bbox -91.0 19.5 -90.0 20.5 --year 2020 --output data/yucatan_lc_2020.tif
```

`fetch_jrc_gsw.py` fetches JRC Global Surface Water (1984–2024) for hydrological
connectivity analysis. The `occurrence` product (% of time a pixel held water)
and `seasonality` (months/year) are most useful for identifying tidal corridors.

```bash
python fetch_jrc_gsw.py --center -90.5 20.0 --buffer-km 25 --output data/yucatan_water.tif
python fetch_jrc_gsw.py --center -90.5 20.0 --product seasonality --output data/yucatan_seasonality.tif
```

Available JRC products: `occurrence`, `seasonality`, `recurrence`, `change`, `transitions`, `extent`.

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

### Infrastructure barriers

`fetch_osm_barriers.py` queries the Overpass API for physical features that may
block landward mangrove migration: roads, seawalls, embankments/levees, dikes,
and aquaculture ponds. Output is **GeoJSON** (not raster) since scoring will use
distance-to-nearest-barrier rather than pixel values.

```bash
python fetch_osm_barriers.py --center -90.5 20.0 --buffer-km 25 --output data/yucatan_barriers.geojson
python fetch_osm_barriers.py --bbox -91.0 19.5 -90.0 20.5 --output data/yucatan_barriers.geojson
```

Note: road coverage is excellent globally; levee/seawall coverage is good in
developed regions but sparse in parts of coastal Southeast Asia and West Africa.
Treat absence of levee features as data uncertainty, not confirmed absence.

> **TODO:** Add Global Dam Watch for upstream dam/reservoir barriers.

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
| `fetch_worldcover.py` | ESA WorldCover 10 m land cover from AWS S3 (COG range reads) |
| `fetch_jrc_gsw.py` | JRC Global Surface Water occurrence/seasonality from CloudFerro |
| `fetch_ghsl.py` | GHSL built-up, urbanisation, population from JRC |
| `fetch_osm_barriers.py` | OSM roads, seawalls, levees, aquaculture via Overpass API → GeoJSON |
| `plot_dem.py` | Renders a DEM GeoTIFF as a colour hillshade terrain map |
| `data/` | Fetched GeoTIFFs (not committed) |
| `figures/` | Rendered map PNGs |
