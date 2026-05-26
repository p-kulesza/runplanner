from __future__ import annotations

from typing import Sequence

from route_engine.config import CALM_HIGHWAYS, MAJOR_HIGHWAYS
from route_engine.routing import route_summary_frame


def evaluate_route(
    graph,
    route_nodes: Sequence[int],
    target_distance_km: float | None = None,
    snap_offsets: Sequence[float] | None = None,
) -> dict[str, float]:
    frame = route_summary_frame(graph, route_nodes)
    total_length = float(frame["length"].sum())
    if total_length <= 0:
        raise ValueError("Route length is zero.")

    major_length = float(frame.loc[frame["highway_normalized"].isin(MAJOR_HIGHWAYS), "length"].sum())
    calm_length = float(frame.loc[frame["highway_normalized"].isin(CALM_HIGHWAYS), "length"].sum())
    signals = int(frame["signal_count_near"].sum())

    major_share = major_length / total_length
    calm_share = calm_length / total_length
    signals_per_km = signals / max(total_length / 1000.0, 0.1)

    score = 100.0
    score -= major_share * 45.0
    score -= min(signals_per_km * 6.0, 30.0)
    score += calm_share * 20.0
    if target_distance_km is not None:
        distance_gap_km = round((total_length / 1000.0) - target_distance_km, 2)
        score -= min(abs(distance_gap_km) * 10.0, 25.0)
    else:
        distance_gap_km = 0.0

    snap_offsets = [float(item) for item in (snap_offsets or [])]
    snap_avg_m = round(sum(snap_offsets) / len(snap_offsets), 1) if snap_offsets else 0.0
    snap_max_m = round(max(snap_offsets), 1) if snap_offsets else 0.0
    score = max(0.0, min(100.0, score))

    return {
        "distance_km": round(total_length / 1000.0, 2),
        "distance_gap_km": distance_gap_km,
        "signals_near_route": float(signals),
        "major_roads_share": round(major_share * 100.0, 1),
        "calm_roads_share": round(calm_share * 100.0, 1),
        "snap_avg_m": snap_avg_m,
        "snap_max_m": snap_max_m,
        "score": round(score, 1),
    }
