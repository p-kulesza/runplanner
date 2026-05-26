from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as ET

from route_engine.config import BASE_DIR

try:
    from supabase import Client, create_client
except ImportError:  # pragma: no cover - optional dependency in local fallback mode
    Client = Any  # type: ignore[assignment]
    create_client = None


ROUTES_DIR = BASE_DIR / "data" / "routes"
ROUTE_LIBRARY_FILE = BASE_DIR / "data" / "routes.json"
ROUTES_RELATIVE_DIR = Path("data") / "routes"
GPX_NAMESPACE = {"gpx": "http://www.topografix.com/GPX/1/1"}
SUPABASE_TABLE = "routes"
MAX_GPX_BYTES = 2 * 1024 * 1024


@dataclass
class ParsedGpx:
    title: str
    points: list[tuple[float, float]]
    distance_km: float
    elevations_m: list[float | None]


def _normalize_elevations(values: list[float | None]) -> list[float | None]:
    if len(values) <= 1:
        return values

    normalized = values[:]
    last_known: float | None = None
    for idx, value in enumerate(normalized):
        if value is not None:
            last_known = value
            continue

        next_known = None
        for later in normalized[idx + 1 :]:
            if later is not None:
                next_known = later
                break

        if last_known is not None:
            normalized[idx] = last_known
        elif next_known is not None:
            normalized[idx] = next_known

    return normalized


def ensure_library() -> None:
    ROUTES_DIR.mkdir(parents=True, exist_ok=True)
    if not ROUTE_LIBRARY_FILE.exists():
        ROUTE_LIBRARY_FILE.write_text("[]", encoding="utf-8")


def _secret_value(name: str) -> str | None:
    env_value = os.getenv(name.upper()) or os.getenv(name)
    if env_value:
        return env_value

    try:
        import streamlit as st

        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        return None
    return None


def supabase_configured() -> bool:
    return bool(_secret_value("supabase_url") and _secret_value("supabase_key") and create_client is not None)


@lru_cache(maxsize=1)
def get_supabase_client() -> Client | None:
    if not supabase_configured():
        return None
    url = _secret_value("supabase_url")
    key = _secret_value("supabase_key")
    if not url or not key or create_client is None:
        return None
    return create_client(url, key)


def _normalize_route_record(route: dict[str, Any]) -> dict[str, Any]:
    route.setdefault("author", "")
    route.setdefault("scheduled_dates", [])
    route.setdefault("groups", [])
    route.setdefault("gpx_xml", "")
    route.setdefault("gpx_path", "")
    return route


def _resolve_route_path(route: dict[str, Any]) -> Path:
    raw_path_value = route.get("gpx_path") or ""
    raw_path = Path(raw_path_value)
    if raw_path_value and raw_path.is_absolute():
        candidate = ROUTES_DIR / raw_path.name
        if candidate.exists():
            return candidate
        return raw_path
    return BASE_DIR / raw_path if raw_path_value else ROUTES_DIR / f"{route['id']}.gpx"


def _relative_route_path(path: Path) -> Path:
    try:
        return path.relative_to(BASE_DIR)
    except ValueError:
        return ROUTES_RELATIVE_DIR / path.name


def _route_gpx_bytes(route: dict[str, Any]) -> bytes:
    gpx_xml = route.get("gpx_xml")
    if gpx_xml:
        return str(gpx_xml).encode("utf-8")
    return _resolve_route_path(route).read_bytes()


def load_routes_from_disk() -> list[dict[str, Any]]:
    ensure_library()
    routes = json.loads(ROUTE_LIBRARY_FILE.read_text(encoding="utf-8"))
    normalized = [_normalize_route_record(route) for route in routes]
    for route in normalized:
        route["gpx_path"] = str(_resolve_route_path(route))
    return sorted(normalized, key=lambda item: item.get("title", "").lower())


def _load_routes_from_supabase() -> list[dict[str, Any]]:
    client = get_supabase_client()
    if client is None:
        return []
    response = client.table(SUPABASE_TABLE).select("*").execute()
    rows = response.data or []
    normalized = [_normalize_route_record(dict(row)) for row in rows]
    return sorted(normalized, key=lambda item: item.get("title", "").lower())


def load_routes() -> list[dict[str, Any]]:
    if supabase_configured():
        return _load_routes_from_supabase()
    return load_routes_from_disk()


def _route_payload_for_storage(route: dict[str, Any]) -> dict[str, Any]:
    route_copy = dict(route)
    route_copy = _normalize_route_record(route_copy)
    route_copy["distance_km"] = float(route_copy.get("distance_km", 0.0))
    route_copy["scheduled_dates"] = list(route_copy.get("scheduled_dates", []))
    route_copy["groups"] = list(route_copy.get("groups", []))
    route_copy["author"] = str(route_copy.get("author", ""))
    route_copy["title"] = str(route_copy.get("title", ""))
    route_copy["filename"] = str(route_copy.get("filename", ""))
    route_copy["created_at"] = str(route_copy.get("created_at", date.today().isoformat()))
    route_copy["gpx_xml"] = route_copy.get("gpx_xml") or _route_gpx_bytes(route_copy).decode("utf-8", errors="replace")
    route_copy["gpx_path"] = str(_relative_route_path(_resolve_route_path(route_copy)))
    return route_copy


def _save_routes_to_disk(routes: list[dict[str, Any]]) -> None:
    ensure_library()
    normalized_routes: list[dict[str, Any]] = []
    for route in routes:
        route_copy = _route_payload_for_storage(route)
        target_path = _resolve_route_path(route_copy)
        if route_copy.get("gpx_xml"):
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(route_copy["gpx_xml"].encode("utf-8"))
        normalized_routes.append(route_copy)
    ROUTE_LIBRARY_FILE.write_text(json.dumps(normalized_routes, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_routes_to_supabase(routes: list[dict[str, Any]]) -> None:
    client = get_supabase_client()
    if client is None:
        raise RuntimeError("Supabase client is not configured.")

    payload = [_route_payload_for_storage(route) for route in routes]
    existing_rows = client.table(SUPABASE_TABLE).select("id").execute().data or []
    existing_ids = {row["id"] for row in existing_rows}
    new_ids = {row["id"] for row in payload}

    if payload:
        client.table(SUPABASE_TABLE).upsert(payload).execute()

    for deleted_id in sorted(existing_ids - new_ids):
        client.table(SUPABASE_TABLE).delete().eq("id", deleted_id).execute()


def save_routes(routes: list[dict[str, Any]]) -> None:
    if supabase_configured():
        _save_routes_to_supabase(routes)
        return
    _save_routes_to_disk(routes)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    hav = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    return 2 * radius_km * asin(sqrt(hav))


def _distance_km(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    return round(
        sum(_haversine_km(lat1, lon1, lat2, lon2) for (lat1, lon1), (lat2, lon2) in zip(points, points[1:])),
        2,
    )


def parse_gpx_bytes(raw_bytes: bytes, fallback_title: str) -> ParsedGpx:
    if len(raw_bytes) > MAX_GPX_BYTES:
        raise ValueError("Plik GPX jest zbyt duży.")

    root = ET.fromstring(raw_bytes)
    name_node = root.find(".//gpx:trk/gpx:name", GPX_NAMESPACE)
    title = name_node.text.strip() if name_node is not None and name_node.text else fallback_title

    points: list[tuple[float, float]] = []
    elevations_m: list[float | None] = []
    for trackpoint in root.findall(".//gpx:trkpt", GPX_NAMESPACE):
        lat = trackpoint.attrib.get("lat")
        lon = trackpoint.attrib.get("lon")
        if lat is None or lon is None:
            continue
        points.append((float(lat), float(lon)))
        ele_node = trackpoint.find("gpx:ele", GPX_NAMESPACE)
        elevations_m.append(float(ele_node.text) if ele_node is not None and ele_node.text else None)

    if len(points) < 2:
        for routepoint in root.findall(".//gpx:rtept", GPX_NAMESPACE):
            lat = routepoint.attrib.get("lat")
            lon = routepoint.attrib.get("lon")
            if lat is None or lon is None:
                continue
            points.append((float(lat), float(lon)))
            ele_node = routepoint.find("gpx:ele", GPX_NAMESPACE)
            elevations_m.append(float(ele_node.text) if ele_node is not None and ele_node.text else None)

    if len(points) < 2:
        raise ValueError("Plik GPX nie zawiera poprawnego przebiegu trasy.")

    return ParsedGpx(
        title=title,
        points=points,
        distance_km=_distance_km(points),
        elevations_m=_normalize_elevations(elevations_m),
    )


def import_gpx_file(
    upload_name: str,
    raw_bytes: bytes,
    author: str,
    scheduled_date: str,
    custom_title: str | None = None,
) -> dict[str, Any]:
    ensure_library()
    if len(raw_bytes) > MAX_GPX_BYTES:
        raise ValueError("Plik GPX jest zbyt duży.")
    parsed = parse_gpx_bytes(raw_bytes, fallback_title=Path(upload_name).stem)
    route_id = str(uuid.uuid4())
    target_path = ROUTES_DIR / f"{route_id}.gpx"
    target_path.write_bytes(raw_bytes)

    return {
        "id": route_id,
        "title": custom_title.strip() if custom_title and custom_title.strip() else parsed.title,
        "filename": upload_name,
        "author": author.strip(),
        "distance_km": parsed.distance_km,
        "scheduled_dates": [scheduled_date] if scheduled_date else [],
        "groups": [],
        "gpx_xml": raw_bytes.decode("utf-8", errors="replace"),
        "gpx_path": str(_relative_route_path(target_path)),
        "created_at": date.today().isoformat(),
    }


def route_gpx_bytes(route: dict[str, Any]) -> bytes:
    return _route_gpx_bytes(route)


def route_points(route: dict[str, Any]) -> list[tuple[float, float]]:
    parsed = parse_gpx_bytes(_route_gpx_bytes(route), fallback_title=route["title"])
    return parsed.points


def route_analysis(route: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_gpx_bytes(_route_gpx_bytes(route), fallback_title=route["title"])
    points = parsed.points
    elevations = parsed.elevations_m

    ascent_m = 0.0
    descent_m = 0.0
    for prev, curr in zip(elevations, elevations[1:]):
        if prev is None or curr is None:
            continue
        delta = curr - prev
        if delta > 0:
            ascent_m += delta
        elif delta < 0:
            descent_m += abs(delta)

    known_elevations = [value for value in elevations if value is not None]
    cumulative_distance_km = [0.0]
    running = 0.0
    for (lat1, lon1), (lat2, lon2) in zip(points, points[1:]):
        running += _haversine_km(lat1, lon1, lat2, lon2)
        cumulative_distance_km.append(round(running, 3))

    return {
        "points": points,
        "distance_km": parsed.distance_km,
        "elevations_m": elevations,
        "profile_rows": [
            {"distance_km": distance, "elevation_m": elevation}
            for distance, elevation in zip(cumulative_distance_km, elevations)
            if elevation is not None
        ],
        "ascent_m": round(ascent_m),
        "descent_m": round(descent_m),
        "min_elevation_m": round(min(known_elevations), 1) if known_elevations else None,
        "max_elevation_m": round(max(known_elevations), 1) if known_elevations else None,
        "point_count": len(points),
        "start_point": points[0],
        "end_point": points[-1],
        "has_elevation": bool(known_elevations),
    }


def delete_route_file(route: dict[str, Any]) -> None:
    if supabase_configured():
        return
    gpx_path = _resolve_route_path(route)
    if gpx_path.exists():
        gpx_path.unlink()
