"""
fetch_osm_barriers.py — Fetch infrastructure barrier features from OpenStreetMap.

Queries the Overpass API for physical features that may block landward mangrove
migration within a bounding box. Returns a GeoJSON file containing roads,
seawalls, embankments/levees, dikes, and aquaculture ponds.

Output is vector (GeoJSON), not raster, because:
  - These are discrete linear/polygon features, not continuous fields.
  - Scoring will use distance-to-nearest-barrier, not pixel values.
  - GeoJSON is directly inspectable in QGIS, geojson.io, etc.

OSM tags fetched:
  highway=*                  Roads of all classes (the primary linear barrier)
  man_made=seawall           Coastal armoring
  man_made=embankment        Raised earthworks (levees, bunds)
  barrier=dike               Flood dikes
  barrier=levee              Flood levees
  landuse=aquaculture        Aquaculture ponds (major barrier in SE Asia)

Note on coverage: road coverage in OSM is excellent globally. Levee/seawall
coverage is good in developed regions but sparse in parts of coastal Southeast
Asia, West Africa, and the Ganges-Brahmaputra delta — exactly the high-priority
mangrove areas. Treat absence of levee features as data uncertainty, not
confirmed absence.

TODO: Add Global Dam Watch for dam/reservoir barriers upstream of tidal zones.
"""

import json
import math
import time
from pathlib import Path
from typing import Optional

import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Seconds to wait between retries on rate-limit (HTTP 429) or server errors.
_RETRY_DELAYS = [5, 15, 30]

# OSM tag groups to fetch. Each entry becomes a set of Overpass union clauses.
_TAG_GROUPS = {
    "road": [
        'way["highway"]',
    ],
    "seawall": [
        'way["man_made"="seawall"]',
        'relation["man_made"="seawall"]',
    ],
    "embankment": [
        'way["man_made"="embankment"]',
    ],
    "dike": [
        'way["barrier"="dike"]',
        'way["barrier"="levee"]',
    ],
    "aquaculture": [
        'way["landuse"="aquaculture"]',
        'relation["landuse"="aquaculture"]',
    ],
}


def _build_query(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> str:
    # Overpass bbox order: south, west, north, east
    bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    clauses = "\n  ".join(
        f"{clause}({bbox});"
        for group in _TAG_GROUPS.values()
        for clause in group
    )
    return f"""
[out:json][timeout:60][bbox:{bbox}];
(
  {clauses}
);
out geom;
""".strip()


def _overpass_request(query: str, timeout: int = 90) -> dict:
    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            print(f"[OSM] Retrying in {delay}s...")
            time.sleep(delay)
        try:
            resp = requests.post(
                OVERPASS_URL,
                data={"data": query},
                timeout=timeout,
                headers={"User-Agent": "mango-mangrove-tool/0.1"},
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                print(f"[OSM] Server returned {resp.status_code}.")
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            print(f"[OSM] Request timed out (attempt {attempt + 1}).")
        except requests.exceptions.RequestException as exc:
            print(f"[OSM] Request error: {exc}")

    raise RuntimeError(
        "Overpass API request failed after retries. "
        "The server may be overloaded — try again later or reduce the AOI size."
    )


def _tag_barrier_type(tags: dict) -> str:
    """Infer a human-readable barrier category from OSM tags."""
    if tags.get("man_made") == "seawall":
        return "seawall"
    if tags.get("man_made") == "embankment":
        return "embankment"
    if tags.get("barrier") in ("dike", "levee"):
        return tags["barrier"]
    if tags.get("landuse") == "aquaculture":
        return "aquaculture"
    if "highway" in tags:
        return f"road:{tags['highway']}"
    return "unknown"


def _element_to_feature(element: dict) -> Optional[dict]:
    """Convert a single Overpass element to a GeoJSON Feature, or None if unrenderable."""
    etype = element.get("type")
    tags = element.get("tags", {})
    barrier_type = _tag_barrier_type(tags)

    props = {
        "osm_id": element.get("id"),
        "osm_type": etype,
        "barrier_type": barrier_type,
        **{k: v for k, v in tags.items()},
    }

    if etype == "way":
        nodes = element.get("geometry", [])
        if len(nodes) < 2:
            return None
        coords = [[n["lon"], n["lat"]] for n in nodes]
        # Closed ways with area tags → Polygon; open ways → LineString
        is_area = (
            coords[0] == coords[-1]
            and tags.get("landuse") == "aquaculture"
        )
        geometry = (
            {"type": "Polygon", "coordinates": [coords]}
            if is_area
            else {"type": "LineString", "coordinates": coords}
        )

    elif etype == "relation":
        members = element.get("members", [])
        rings = []
        for m in members:
            if m.get("type") == "way" and "geometry" in m:
                ring = [[n["lon"], n["lat"]] for n in m["geometry"]]
                if len(ring) >= 4 and ring[0] == ring[-1]:
                    rings.append(ring)
        if not rings:
            return None
        geometry = {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}

    else:
        return None

    return {"type": "Feature", "geometry": geometry, "properties": props}


def fetch(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    output_path: str = "osm_barriers.geojson",
) -> str:
    """
    Fetch OSM infrastructure barrier features for a bounding box.

    Parameters
    ----------
    min_lon, min_lat, max_lon, max_lat : float
        Bounding box in WGS84 decimal degrees.
    output_path : str
        Destination GeoJSON path.

    Returns
    -------
    str
        Path to the saved GeoJSON.
    """
    print(f"[OSM] AOI: {min_lon:.4f},{min_lat:.4f} → {max_lon:.4f},{max_lat:.4f}")
    print(f"[OSM] Querying Overpass API...")

    query = _build_query(min_lon, min_lat, max_lon, max_lat)
    data = _overpass_request(query)

    elements = data.get("elements", [])
    print(f"[OSM] Elements returned: {len(elements)}")

    features = []
    for el in elements:
        feat = _element_to_feature(el)
        if feat is not None:
            features.append(feat)

    # Summary by barrier type
    from collections import Counter
    counts = Counter(f["properties"]["barrier_type"] for f in features)
    for btype, n in sorted(counts.items()):
        print(f"  {btype}: {n}")

    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "bbox": [min_lon, min_lat, max_lon, max_lat],
            "source": "OpenStreetMap via Overpass API",
            "osm_timestamp": data.get("osm3s", {}).get("timestamp_osm_base", "unknown"),
        },
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(geojson, f)

    print(f"[OSM] Saved: {output_path}  ({len(features)} features)")
    return output_path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch OSM infrastructure barriers for an AOI.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    aoi = parser.add_mutually_exclusive_group(required=True)
    aoi.add_argument("--center", nargs=2, metavar=("LON", "LAT"), type=float)
    aoi.add_argument("--bbox", nargs=4,
                     metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"), type=float)
    parser.add_argument("--buffer-km", type=float, default=25.0)
    parser.add_argument("--output", default="osm_barriers.geojson")

    args = parser.parse_args()

    if args.center:
        lon, lat = args.center
        buf = args.buffer_km
        d_lat = buf / 111.32
        d_lon = buf / (111.32 * math.cos(math.radians(lat)))
        bbox = (lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat)
    else:
        bbox = tuple(args.bbox)

    fetch(*bbox, output_path=args.output)


if __name__ == "__main__":
    main()
