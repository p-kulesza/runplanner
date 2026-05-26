from __future__ import annotations

from typing import Tuple

import osmnx as ox


def geocode_place_center(place_name: str) -> Tuple[float, float]:
    gdf = ox.geocode_to_gdf(place_name)
    if gdf.empty:
        raise ValueError(f"Could not geocode place: {place_name}")

    centroid = gdf.to_crs(3857).geometry.centroid.to_crs(4326).iloc[0]
    return float(centroid.y), float(centroid.x)

