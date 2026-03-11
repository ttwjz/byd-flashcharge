"""Reverse geocoding module for BYD Flash Charge stations.

Dual-backend design:
  1. Primary: Amap (高德地图) reverse geocoding API - most accurate
  2. Fallback: Offline Point-in-Polygon using DataV GeoJSON + shapely

When Amap quota is exhausted (infocode 10003/10004/10044), automatically
switches to offline PiP for the rest of the run.

Set AMAP_API_KEY in environment before use.
"""

import json
import os
import time
import logging
import requests
from functools import lru_cache
from shapely.geometry import Point, shape
from shapely.prepared import prep

AMAP_API_KEY = os.environ.get("AMAP_API_KEY", "")

AMAP_REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"
MAPS_DIR = os.path.join(os.path.dirname(__file__), "public", "static", "maps")

_amap_exhausted = False

# Amap infocodes that indicate quota exhaustion
_QUOTA_CODES = {"10003", "10004", "10044"}

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backend 1: Amap API
# ---------------------------------------------------------------------------

def _amap_geocode(lat: float, lng: float) -> dict:
    """Call Amap reverse geocoding API. Returns {province, city} or {} on failure."""
    global _amap_exhausted

    if not AMAP_API_KEY or _amap_exhausted:
        return {}

    try:
        params = {
            "key": AMAP_API_KEY,
            "location": f"{lng},{lat}",
            "extensions": "base",
            "output": "json",
        }

        resp = requests.get(AMAP_REGEO_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        infocode = data.get("infocode", "")
        if infocode in _QUOTA_CODES:
            log.warning(f"Amap quota exhausted (infocode={infocode}), switching to offline PiP")
            _amap_exhausted = True
            return {}

        if data.get("status") != "1":
            log.warning(f"Amap API error: {data.get('info')} (infocode={infocode})")
            return {}

        addr = data.get("regeocode", {}).get("addressComponent", {})
        province = addr.get("province", "")
        city = addr.get("city", "")

        if isinstance(province, list):
            province = ""
        if isinstance(city, list):
            city = province

        return {"province": province, "city": city or province}

    except Exception as e:
        log.error(f"Amap request failed at ({lat}, {lng}): {e}")
        return {}


# ---------------------------------------------------------------------------
# Backend 2: Offline Point-in-Polygon
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_national_polygons():
    """Load national GeoJSON and build prepared polygons for province lookup."""
    path = os.path.join(MAPS_DIR, "100000_full.json")
    if not os.path.exists(path):
        log.error(f"National GeoJSON not found: {path}")
        return []

    with open(path, encoding="utf-8") as f:
        geo = json.load(f)

    polygons = []
    for feature in geo.get("features", []):
        name = feature.get("properties", {}).get("name", "")
        adcode = str(feature.get("properties", {}).get("adcode", ""))
        try:
            geom = shape(feature["geometry"])
            polygons.append((name, adcode, prep(geom), geom))
        except Exception:
            continue

    log.info(f"Loaded national PiP data: {len(polygons)} provinces")
    return polygons


@lru_cache(maxsize=40)
def _load_province_polygons(adcode: str):
    """Load a province's GeoJSON and build prepared polygons for city lookup."""
    path = os.path.join(MAPS_DIR, f"{adcode}_full.json")
    if not os.path.exists(path):
        return []

    with open(path, encoding="utf-8") as f:
        geo = json.load(f)

    polygons = []
    for feature in geo.get("features", []):
        name = feature.get("properties", {}).get("name", "")
        try:
            geom = shape(feature["geometry"])
            polygons.append((name, prep(geom)))
        except Exception:
            continue

    return polygons


def _pip_geocode(lat: float, lng: float) -> dict:
    """Offline point-in-polygon geocoding using DataV GeoJSON + shapely."""
    point = Point(lng, lat)

    national = _load_national_polygons()
    if not national:
        return {}

    province_name = ""
    province_adcode = ""
    for name, adcode, prepared, _ in national:
        if prepared.contains(point):
            province_name = name
            province_adcode = adcode
            break

    if not province_name:
        min_dist = float("inf")
        for name, adcode, _, geom in national:
            d = geom.distance(point)
            if d < min_dist:
                min_dist = d
                province_name = name
                province_adcode = adcode
        if min_dist > 1.0:
            return {}

    _MUNICIPALITIES = {"110000", "120000", "310000", "500000"}
    if province_adcode in _MUNICIPALITIES:
        return {"province": province_name, "city": province_name}

    city_name = province_name
    city_polygons = _load_province_polygons(province_adcode)
    for name, prepared in city_polygons:
        if prepared.contains(point):
            city_name = name
            break

    return {"province": province_name, "city": city_name}


# ---------------------------------------------------------------------------
# Unified interface
# ---------------------------------------------------------------------------

def geocode_station(lat: float, lng: float) -> dict:
    """Geocode a station coordinate. Returns {"province": "...", "city": "..."}.

    Tries Amap API first; falls back to offline PiP when quota is exhausted.
    """
    result = _amap_geocode(lat, lng)
    if result:
        return result

    return _pip_geocode(lat, lng)


def geocode_pending_stations(conn, delay: float = 0.1):
    """Geocode all stations where geocoded=0. Database acts as cache.

    Already-geocoded stations are skipped. Can be interrupted and resumed.
    """
    stations = conn.execute(
        "SELECT id, lat, lng FROM stations WHERE geocoded = 0"
    ).fetchall()

    if not stations:
        log.info("All stations already geocoded.")
        return 0

    backend = "Amap API" if (AMAP_API_KEY and not _amap_exhausted) else "offline PiP"
    log.info(f"Geocoding {len(stations)} pending stations (starting with {backend})...")

    success = 0

    for i, s in enumerate(stations):
        result = geocode_station(s["lat"], s["lng"])
        if not result:
            if not _amap_exhausted:
                time.sleep(delay)
            continue

        conn.execute("""
            UPDATE stations SET province = ?, city = ?, geocoded = 1
            WHERE id = ?
        """, (result.get("province", ""), result.get("city", ""), s["id"]))

        success += 1

        if (i + 1) % 50 == 0:
            conn.commit()
            backend = "PiP" if _amap_exhausted else "API"
            log.info(f"  Geocoded {i+1}/{len(stations)} ({success} ok, via {backend})")

        if not _amap_exhausted:
            time.sleep(delay)

    conn.commit()
    log.info(f"Geocoding done: {success}/{len(stations)} successful")
    return success


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if not AMAP_API_KEY:
        print("高德 API Key 未设置，将使用离线 PiP 模式")
        print("如需使用高德 API: export AMAP_API_KEY=your_key_here")
    else:
        print(f"使用高德 API (Key: {AMAP_API_KEY[:8]}...)")

    from database import get_db
    conn = get_db()
    try:
        geocode_pending_stations(conn)
    finally:
        conn.close()
