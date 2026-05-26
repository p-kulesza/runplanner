from __future__ import annotations

from typing import Any
import os

import geopandas as gpd
import osmnx as ox
from shapely.geometry import LineString

from route_engine.config import (
    CACHE_DIR,
    CALM_ROAD_BONUS,
    CALM_HIGHWAYS,
    DEFAULT_SIGNAL_BUFFER_METERS,
    MAJOR_HIGHWAYS,
    MAIN_ROAD_PENALTY,
    SAFE_HIGHWAYS,
    SIGNAL_PENALTY,
    UNKNOWN_HIGHWAY_PENALTY,
)

os.makedirs(CACHE_DIR, exist_ok=True)
ox.settings.use_cache = True
ox.settings.cache_folder = str(CACHE_DIR)


def _normalize_highway(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0]).lower()
    if value is None:
        return "unknown"
    return str(value).lower()


def _signal_mask(series: gpd.GeoSeries) -> gpd.GeoSeries:
    return series.fillna("").astype(str).str.contains("traffic_signals", case=False)


def _edge_geometry_or_straight(row: Any, node_points: gpd.GeoSeries) -> LineString:
    geometry = row.get("geometry")
    if geometry is not None:
        return geometry
    return LineString([node_points.loc[row["u"]], node_points.loc[row["v"]]])


def _edge_projected_length(row: Any, node_points: gpd.GeoSeries) -> float:
    geometry = _edge_geometry_or_straight(row, node_points)
    return float(geometry.length)


def _build_signal_counts(graph) -> dict[tuple[int, int, int], int]:
    projected_graph = ox.project_graph(graph)
    nodes_gdf, edges_gdf = ox.graph_to_gdfs(projected_graph, nodes=True, edges=True)

    if edges_gdf.empty:
        return {}

    signal_nodes = nodes_gdf[_signal_mask(nodes_gdf.get("highway"))].copy()
    if signal_nodes.empty:
        return {(u, v, k): 0 for u, v, k in edges_gdf.index}

    signal_buffers = signal_nodes[["geometry"]].copy()
    signal_buffers["geometry"] = signal_buffers.geometry.buffer(DEFAULT_SIGNAL_BUFFER_METERS)
    signal_buffers["signal_id"] = signal_buffers.index.astype(str)

    edges_reset = edges_gdf.reset_index()
    edges_reset["geometry"] = edges_reset.apply(
        lambda row: _edge_geometry_or_straight(row, nodes_gdf.geometry),
        axis=1,
    )
    edges_geom = gpd.GeoDataFrame(edges_reset, geometry="geometry", crs=edges_gdf.crs)

    joined = gpd.sjoin(
        edges_geom[["u", "v", "key", "geometry"]],
        signal_buffers[["signal_id", "geometry"]],
        predicate="intersects",
        how="left",
    )
    counts = joined.groupby(["u", "v", "key"])["signal_id"].nunique().fillna(0).astype(int)
    return counts.to_dict()


def add_run_costs(graph):
    projected_graph = ox.project_graph(graph)
    projected_nodes, projected_edges = ox.graph_to_gdfs(projected_graph, nodes=True, edges=True)
    edge_lengths: dict[tuple[int, int, int], float] = {}

    if not projected_edges.empty:
        projected_edges_reset = projected_edges.reset_index()
        projected_edges_reset["true_length_m"] = projected_edges_reset.apply(
            lambda row: _edge_projected_length(row, projected_nodes.geometry),
            axis=1,
        )
        edge_lengths = {
            (int(row["u"]), int(row["v"]), int(row["key"])): float(row["true_length_m"])
            for _, row in projected_edges_reset.iterrows()
        }

    signal_counts = _build_signal_counts(graph)

    for u, v, key, data in graph.edges(keys=True, data=True):
        highway = _normalize_highway(data.get("highway"))
        length = float(edge_lengths.get((u, v, key), data.get("length", 0.0)))
        signal_count = int(signal_counts.get((u, v, key), 0))

        cost = length
        if highway in MAJOR_HIGHWAYS:
            cost += MAIN_ROAD_PENALTY
        elif highway in CALM_HIGHWAYS:
            cost = max(1.0, cost - CALM_ROAD_BONUS)
        elif highway not in SAFE_HIGHWAYS:
            cost += UNKNOWN_HIGHWAY_PENALTY

        cost += signal_count * SIGNAL_PENALTY

        data["highway_normalized"] = highway
        data["signal_count_near"] = signal_count
        data["true_length_m"] = float(length)
        data["run_cost"] = float(cost)

    return graph


def load_city_graph(place_name: str):
    graph = ox.graph_from_place(place_name, network_type="walk", simplify=True)
    if graph.number_of_nodes() == 0:
        raise ValueError(f"No walkable graph found for place: {place_name}")
    return add_run_costs(graph)
