from __future__ import annotations

from typing import Sequence
from xml.etree.ElementTree import Element, SubElement, tostring

from route_engine.routing import route_coordinates


def route_to_gpx_bytes(graph, route_nodes: Sequence[int], name: str = "Run Route") -> bytes:
    coords = route_coordinates(graph, route_nodes)

    gpx = Element("gpx", version="1.1", creator="Run Route Planner", xmlns="http://www.topografix.com/GPX/1/1")
    trk = SubElement(gpx, "trk")
    SubElement(trk, "name").text = name
    trkseg = SubElement(trk, "trkseg")

    for lat, lon in coords:
        SubElement(trkseg, "trkpt", lat=f"{lat:.7f}", lon=f"{lon:.7f}")

    return tostring(gpx, encoding="utf-8", xml_declaration=True)
