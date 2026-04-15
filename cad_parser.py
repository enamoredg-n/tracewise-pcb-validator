"""
cad_parser.py - lightweight ASCII DXF geometry parser

This parser is intentionally small and dependency-free so the app can
validate simple DXF drawings without requiring external CAD libraries.
It currently extracts:
  - CIRCLE entities (treated as holes/features)
  - LINE entities
  - LWPOLYLINE entities

The parsed output is designed for rule-based validation, not full CAD
fidelity. Binary DXF and advanced entity types are not supported yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class Circle:
    center_x: float
    center_y: float
    radius: float

    @property
    def diameter(self) -> float:
        return self.radius * 2.0


@dataclass
class Line:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class Polyline:
    points: list[tuple[float, float]]
    closed: bool = False


def _pairs(lines: list[str]) -> Iterable[tuple[str, str]]:
    for i in range(0, len(lines) - 1, 2):
        yield lines[i].strip(), lines[i + 1].strip()


def _update_bbox(bbox: list[float] | None, x: float, y: float) -> list[float]:
    if bbox is None:
        return [x, y, x, y]
    bbox[0] = min(bbox[0], x)
    bbox[1] = min(bbox[1], y)
    bbox[2] = max(bbox[2], x)
    bbox[3] = max(bbox[3], y)
    return bbox


def _bbox_from_entities(circles: list[Circle], lines: list[Line], polylines: list[Polyline]):
    bbox = None

    for circle in circles:
        bbox = _update_bbox(bbox, circle.center_x - circle.radius, circle.center_y - circle.radius)
        bbox = _update_bbox(bbox, circle.center_x + circle.radius, circle.center_y + circle.radius)

    for line in lines:
        bbox = _update_bbox(bbox, line.x1, line.y1)
        bbox = _update_bbox(bbox, line.x2, line.y2)

    for polyline in polylines:
        for x, y in polyline.points:
            bbox = _update_bbox(bbox, x, y)

    return bbox


def _finalize_circle(data: dict[str, float], circles: list[Circle]):
    if {"10", "20", "40"} <= data.keys():
        circles.append(Circle(data["10"], data["20"], abs(data["40"])))


def _finalize_line(data: dict[str, float], lines: list[Line]):
    if {"10", "20", "11", "21"} <= data.keys():
        lines.append(Line(data["10"], data["20"], data["11"], data["21"]))


def _finalize_lwpolyline(vertices: list[tuple[float, float]], flags: int, polylines: list[Polyline]):
    if vertices:
        polylines.append(Polyline(points=vertices[:], closed=bool(flags & 1)))


def parse_dxf_text(text: str) -> dict:
    if "\x00" in text:
        raise ValueError("Binary DXF is not supported yet. Please export as ASCII DXF.")

    lines_raw = text.splitlines()
    if len(lines_raw) < 2:
        raise ValueError("DXF file appears to be empty or invalid.")

    circles: list[Circle] = []
    lines: list[Line] = []
    polylines: list[Polyline] = []

    in_entities = False
    current_type = None
    current_data: dict[str, float] = {}
    current_vertices: list[tuple[float, float]] = []
    current_flags = 0
    pending_x = None

    def flush_current():
        nonlocal current_type, current_data, current_vertices, current_flags, pending_x
        if current_type == "CIRCLE":
            _finalize_circle(current_data, circles)
        elif current_type == "LINE":
            _finalize_line(current_data, lines)
        elif current_type == "LWPOLYLINE":
            _finalize_lwpolyline(current_vertices, current_flags, polylines)
        current_type = None
        current_data = {}
        current_vertices = []
        current_flags = 0
        pending_x = None

    for code, value in _pairs(lines_raw):
        if code == "0" and value == "SECTION":
            continue
        if code == "2" and value == "ENTITIES":
            in_entities = True
            continue
        if in_entities and code == "0" and value == "ENDSEC":
            flush_current()
            in_entities = False
            continue
        if not in_entities:
            continue

        if code == "0":
            flush_current()
            current_type = value
            continue

        if current_type not in {"CIRCLE", "LINE", "LWPOLYLINE"}:
            continue

        if current_type in {"CIRCLE", "LINE"} and code in {"10", "20", "11", "21", "40"}:
            try:
                current_data[code] = float(value)
            except ValueError:
                pass
            continue

        if current_type == "LWPOLYLINE":
            if code == "70":
                try:
                    current_flags = int(value)
                except ValueError:
                    current_flags = 0
            elif code == "10":
                try:
                    pending_x = float(value)
                except ValueError:
                    pending_x = None
            elif code == "20" and pending_x is not None:
                try:
                    current_vertices.append((pending_x, float(value)))
                except ValueError:
                    pass
                pending_x = None

    flush_current()

    bbox = _bbox_from_entities(circles, lines, polylines)
    if bbox is None:
        raise ValueError("No supported DXF geometry found. Add circles, lines, or polylines.")

    min_x, min_y, max_x, max_y = bbox
    return {
        "circles": circles,
        "lines": lines,
        "polylines": polylines,
        "bbox": {
            "min_x": min_x,
            "min_y": min_y,
            "max_x": max_x,
            "max_y": max_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
        },
        "stats": {
            "n_circles": len(circles),
            "n_lines": len(lines),
            "n_polylines": len(polylines),
        },
    }


def parse_dxf_bytes(payload: bytes) -> dict:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        text = payload.decode("latin-1")
    return parse_dxf_text(text)
