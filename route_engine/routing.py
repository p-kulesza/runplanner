from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Sequence

import networkx as nx
import osmnx as ox
import pandas as pd


def nearest_node(graph, lat: float, lon: float) -> int:
    return int(ox.distance.nearest_nodes(graph, X=lon, Y=lat))


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6371000.0
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)

    hav = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    return 2 * radius_m * asin(sqrt(hav))


def snap_points_to_graph(graph, points: Sequence[tuple[float, float]]) -> list[dict[str, float | int]]:
    snapped: list[dict[str, float | int]] = []

    for lat, lon in points:
        node_id = nearest_node(graph, lat, lon)
        node = graph.nodes[node_id]
        snapped_lat = float(node["y"])
        snapped_lon = float(node["x"])
        snapped.append(
            {
                "node_id": node_id,
                "input_lat": float(lat),
                "input_lon": float(lon),
                "snapped_lat": snapped_lat,
                "snapped_lon": snapped_lon,
                "offset_m": round(_haversine_meters(lat, lon, snapped_lat, snapped_lon), 1),
            }
        )

    return snapped


def build_full_route(graph, points: Sequence[tuple[float, float]], weight: str = "run_cost") -> list[int]:
    if len(points) < 2:
        raise ValueError("At least two points are required to compute a route.")

    route_nodes: list[int] = []
    nearest_nodes = [int(item["node_id"]) for item in snap_points_to_graph(graph, points)]

    for idx in range(len(nearest_nodes) - 1):
        source = nearest_nodes[idx]
        target = nearest_nodes[idx + 1]
        segment = nx.shortest_path(graph, source=source, target=target, weight=weight)

        if idx > 0:
            segment = segment[1:]
        route_nodes.extend(segment)

    return route_nodes


def route_edges_gdf(graph, route_nodes: Sequence[int]):
    if len(route_nodes) < 2:
        raise ValueError("A route must contain at least two nodes.")
    return ox.routing.route_to_gdf(graph, route_nodes, weight="run_cost")


def route_coordinates(graph, route_nodes: Sequence[int]) -> list[tuple[float, float]]:
    gdf = route_edges_gdf(graph, route_nodes)
    coords: list[tuple[float, float]] = []

    for _, edge in gdf.iterrows():
        geometry = edge.geometry
        if geometry is None:
            continue
        for lon, lat in geometry.coords:
            if not coords or coords[-1] != (lat, lon):
                coords.append((lat, lon))

    if not coords:
        raise ValueError("Could not derive route coordinates from geometry.")

    return coords


def route_summary_frame(graph, route_nodes: Sequence[int]) -> pd.DataFrame:
    gdf = route_edges_gdf(graph, route_nodes)
    frame = pd.DataFrame(gdf.drop(columns="geometry"))
    if "true_length_m" in frame:
        frame["length"] = frame["true_length_m"].fillna(frame["length"]).astype(float)
    else:
        frame["length"] = frame["length"].astype(float)
    frame["signal_count_near"] = frame["signal_count_near"].fillna(0).astype(int)
    frame["highway_normalized"] = frame["highway_normalized"].fillna("unknown")
    return frame
