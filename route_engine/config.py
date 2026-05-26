from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "data" / "cache"
CLUB_DATA_FILE = BASE_DIR / "data" / "club_sessions.json"

DEFAULT_CITY = "Białystok, Poland"
DEFAULT_ZOOM = 13
DEFAULT_SIGNAL_BUFFER_METERS = 25

MAJOR_HIGHWAYS = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
}

CALM_HIGHWAYS = {
    "footway",
    "path",
    "pedestrian",
    "living_street",
    "residential",
    "service",
    "track",
    "steps",
    "cycleway",
}

SAFE_HIGHWAYS = CALM_HIGHWAYS | {"tertiary", "unclassified"}

MAIN_ROAD_PENALTY = 120.0
SIGNAL_PENALTY = 35.0
CALM_ROAD_BONUS = 20.0
UNKNOWN_HIGHWAY_PENALTY = 15.0
