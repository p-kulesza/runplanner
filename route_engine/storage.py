from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, timedelta
from typing import Any

from route_engine.config import CLUB_DATA_FILE, DEFAULT_CITY


def _next_sunday() -> str:
    today = date.today()
    days_ahead = (6 - today.weekday()) % 7
    target = today if days_ahead == 0 else today + timedelta(days=days_ahead)
    return target.isoformat()


def default_sessions() -> list[dict[str, Any]]:
    sunday = _next_sunday()
    return [
        {
            "id": "session-sunday-main",
            "title": "Sunday Long Run",
            "date": sunday,
            "meeting_time": "09:00",
            "city": DEFAULT_CITY,
            "meeting_point": "Start przy klubowej kawiarni",
            "notes": "Dwie grupy na trasie glownej i krotszy wariant dla drugiej grupy.",
            "routes": [
                {
                    "slot": "A",
                    "name": "Glowna trasa",
                    "target_distance_km": 16.0,
                    "actual_distance_km": None,
                    "distance_gap_km": None,
                    "quality_score": None,
                    "signals_near_route": None,
                    "major_roads_share": None,
                    "calm_roads_share": None,
                    "snap_avg_m": None,
                    "snap_max_m": None,
                    "polyline": [],
                    "waypoints": [],
                    "pace_groups": [
                        {"label": "5:10/km", "attendance": 0},
                        {"label": "5:35/km", "attendance": 0},
                    ],
                },
                {
                    "slot": "B",
                    "name": "Krotszy dystans",
                    "target_distance_km": 10.0,
                    "actual_distance_km": None,
                    "distance_gap_km": None,
                    "quality_score": None,
                    "signals_near_route": None,
                    "major_roads_share": None,
                    "calm_roads_share": None,
                    "snap_avg_m": None,
                    "snap_max_m": None,
                    "polyline": [],
                    "waypoints": [],
                    "pace_groups": [
                        {"label": "5:30/km", "attendance": 0},
                        {"label": "6:00/km", "attendance": 0},
                    ],
                },
            ],
        }
    ]


def ensure_storage() -> None:
    CLUB_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not CLUB_DATA_FILE.exists():
        CLUB_DATA_FILE.write_text(
            json.dumps(default_sessions(), ensure_ascii=True, indent=2),
            encoding="utf-8",
        )


def load_sessions() -> list[dict[str, Any]]:
    ensure_storage()
    sessions = json.loads(CLUB_DATA_FILE.read_text(encoding="utf-8"))
    return sorted(sessions, key=lambda item: item.get("date", ""))


def save_sessions(sessions: list[dict[str, Any]]) -> None:
    ensure_storage()
    CLUB_DATA_FILE.write_text(json.dumps(sessions, ensure_ascii=True, indent=2), encoding="utf-8")


def session_template() -> dict[str, Any]:
    session = deepcopy(default_sessions()[0])
    session["id"] = f"session-{date.today().isoformat()}"
    session["title"] = "Nowy trening klubowy"
    session["date"] = _next_sunday()
    return session
