import httpx
import json
from datetime import date, timedelta

STAC_URL = "https://earth-search.aws.element84.com/v1"
CDI_API_URL = "https://drought.emergency.copernicus.eu/gdo/api/"


async def search_sentinel2(bbox: list, date_from: str, date_to: str, max_cloud: int = 30):
    """Search Sentinel-2 L2A scenes via Element84 STAC API.
    bbox: [min_lon, min_lat, max_lon, max_lat]
    """
    payload = {
        "collections": ["sentinel-2-l2a"],
        "bbox": bbox,
        "datetime": f"{date_from}T00:00:00Z/{date_to}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
        "sortby": [{"field": "datetime", "direction": "desc"}],
        "limit": 5,
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{STAC_URL}/search", json=payload, timeout=30)
        r.raise_for_status()
        return r.json()


def compute_ndvi_from_stac_item(item: dict) -> dict:
    """Extract/estimate NDVI statistics from a STAC item.
    
    Phase 0: uses vegetation_percentage as proxy (no COG band download).
    Returns: {ndvi_mean, ndvi_std, cloud_cover, date, scene_id, source}
    """
    props = item.get("properties", {})
    ndvi_mean = props.get("ndvi", None)
    cloud_cover = props.get("eo:cloud_cover", 0)
    acquired = props.get("datetime", "")[:10]
    scene_id = item.get("id", "")

    veg_pct = props.get("s2:vegetation_percentage", 50)
    if ndvi_mean is None:
        # Rough estimate: 0.2 + veg_pct * 0.006 → range ~0.2–0.8
        ndvi_mean = round(0.2 + float(veg_pct) * 0.006, 3)
        ndvi_std = round(0.05 + (100 - float(veg_pct)) * 0.001, 3)
    else:
        ndvi_std = props.get("ndvi_std", round(0.05 + (100 - float(veg_pct)) * 0.001, 3))

    return {
        "ndvi_mean": ndvi_mean,
        "ndvi_std": ndvi_std,
        "cloud_cover": cloud_cover,
        "date": acquired,
        "scene_id": scene_id,
        "source": "sentinel2_stac",
    }


def geojson_bbox(geometry: dict) -> list:
    """Extract bounding box [min_lon, min_lat, max_lon, max_lat] from GeoJSON geometry."""
    coords = []

    def extract_coords(geom):
        t = geom.get("type", "")
        if t == "Point":
            coords.append(geom["coordinates"])
        elif t in ("LineString", "MultiPoint"):
            coords.extend(geom["coordinates"])
        elif t in ("Polygon", "MultiLineString"):
            for ring in geom["coordinates"]:
                coords.extend(ring)
        elif t == "MultiPolygon":
            for poly in geom["coordinates"]:
                for ring in poly:
                    coords.extend(ring)
        elif t == "GeometryCollection":
            for g in geom.get("geometries", []):
                extract_coords(g)
        # If it's a Feature, unwrap
        if "geometry" in geom:
            extract_coords(geom["geometry"])

    extract_coords(geometry)
    if not coords:
        raise ValueError("No coordinates found in geometry")
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return [min(lons), min(lats), max(lons), max(lats)]


async def fetch_ndvi_for_field(field_geometry_geojson: dict, date_from: str, date_to: str) -> dict:
    """Fetch NDVI data for a field geometry from Sentinel-2 STAC."""
    bbox = geojson_bbox(field_geometry_geojson)
    result = await search_sentinel2(bbox, date_from, date_to)
    features = result.get("features", [])
    if not features:
        return {"error": "No Sentinel-2 scenes found for this area/time range", "scenes": []}

    ndvi_results = []
    for item in features[:3]:  # use up to 3 scenes
        ndvi = compute_ndvi_from_stac_item(item)
        ndvi_results.append(ndvi)

    # Return best (most recent, lowest cloud cover)
    best = sorted(ndvi_results, key=lambda x: x.get("cloud_cover", 100))[0]
    return {"best": best, "scenes": ndvi_results}


async def fetch_cdi_for_point(lon: float, lat: float) -> dict:
    """Fetch Combined Drought Indicator for a point from Copernicus GDO.
    Returns CDI value 0–5 (0=no stress, 5=exceptional drought).
    """
    try:
        params = {
            "lon": lon,
            "lat": lat,
            "format": "json",
        }
        async with httpx.AsyncClient() as client:
            # Try the GDO point query API
            r = await client.get(
                f"{CDI_API_URL}cdi/point",
                params=params,
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json()
                cdi_value = data.get("cdi", data.get("value", 0))
                return {"cdi": float(cdi_value), "source": "copernicus_gdo", "lon": lon, "lat": lat}
    except Exception as e:
        pass  # Fall back to neutral value

    # Fallback: return neutral CDI (no stress) with note
    return {
        "cdi": 1.0,
        "source": "fallback_neutral",
        "note": "CDI API unavailable, using neutral value",
        "lon": lon,
        "lat": lat,
    }
