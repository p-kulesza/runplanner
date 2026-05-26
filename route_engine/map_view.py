from __future__ import annotations

from typing import Sequence

import folium

from route_engine.config import DEFAULT_ZOOM
from route_engine.routing import route_coordinates


def build_map(
    center: tuple[float, float],
    route_points: Sequence[tuple[float, float]] | None = None,
    route_nodes: Sequence[int] | None = None,
    graph=None,
):
    fmap = folium.Map(location=center, zoom_start=DEFAULT_ZOOM, control_scale=True, tiles="CartoDB positron")

    if route_points:
        start = route_points[0]
        end = route_points[-1]
        folium.Marker(start, tooltip="Start", icon=folium.Icon(color="green", icon="play")).add_to(fmap)
        folium.Marker(end, tooltip="Meta", icon=folium.Icon(color="red", icon="stop")).add_to(fmap)

        for idx, point in enumerate(route_points[1:-1], start=1):
            folium.CircleMarker(
                point,
                radius=5,
                color="#153ac7",
                fill=True,
                fill_opacity=1.0,
                tooltip=f"Punkt {idx}",
            ).add_to(fmap)

    if graph is not None and route_nodes:
        line = route_coordinates(graph, route_nodes)
        folium.PolyLine(line, color="#153ac7", weight=6, opacity=0.9).add_to(fmap)
        fmap.fit_bounds(line)

    return fmap


def build_polyline_map(
    points: Sequence[tuple[float, float]],
    line_color: str = "#d8c3a5",
    tiles: str = "CartoDB dark_matter",
):
    if not points:
        raise ValueError("Polyline map requires at least one point.")

    center = points[len(points) // 2]
    fmap = folium.Map(location=center, zoom_start=DEFAULT_ZOOM, control_scale=True, tiles=tiles)
    folium.PolyLine(points, color=line_color, weight=5, opacity=0.95).add_to(fmap)
    folium.Marker(points[0], tooltip="Start", icon=folium.Icon(color="lightgray", icon="play")).add_to(fmap)
    folium.Marker(points[-1], tooltip="Meta", icon=folium.Icon(color="lightgray", icon="stop")).add_to(fmap)
    fmap.fit_bounds(points)
    return fmap
