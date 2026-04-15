"""
cad_rules.py - exact rule checks and reference comparison for PCB geometry.
"""

from __future__ import annotations

import math


def _fmt(value: float) -> str:
    return f"{value:.3f}"


def _status(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def _classify_category(source: str, rule: str) -> str:
    text = f"{source} {rule}".lower()
    if source == "Electrical" or any(token in text for token in ("routing", "continuity", "net")):
        return "Electrical"
    if any(
        token in text
        for token in (
            "trace",
            "track",
            "clearance",
            "spacing",
            "plated drill",
            "manufactur",
        )
    ):
        return "Manufacturing"
    return "Mechanical"


def _classify_severity(source: str, rule: str, status: str) -> str:
    if status == "PASS":
        return "Pass"
    if status == "WARN":
        return "Minor"

    text = f"{source} {rule}".lower()
    if source == "Electrical" or any(token in text for token in ("routing", "continuity", "short")):
        return "Critical"
    if any(token in text for token in ("missing component", "unexpected component", "missing drill", "unexpected drill")):
        return "Critical"
    return "Major"


def _result(source: str, rule: str, required: str, found: str, status: str, message: str) -> dict:
    return {
        "Source": source,
        "Category": _classify_category(source, rule),
        "Rule": rule,
        "Required": required,
        "Found": found,
        "Status": status,
        "Severity": _classify_severity(source, rule, status),
        "Message": message,
    }


def _append_bulk_results(
    results: list[dict],
    failures: list[dict],
    *,
    source: str,
    rule: str,
    required: str,
    total_checked: int,
    pass_message: str,
):
    if failures:
        results.extend(failures)
    else:
        results.append(
            _result(
                source,
                rule,
                required,
                f"All {total_checked} passed",
                "PASS",
                pass_message,
            )
        )


def _iter_drills(geometry: dict) -> list:
    return list(geometry.get("drills") or geometry.get("circles") or [])


def _has_plating_metadata(drills: list) -> bool:
    return any(hasattr(drill, "plated") for drill in drills)


def _drill_label(drill, idx: int | None = None) -> str:
    reference = getattr(drill, "reference", "") or ""
    pad_name = getattr(drill, "pad_name", "") or ""
    if reference and reference != "unknown" and pad_name:
        return f"{reference}:{pad_name}"
    if reference and reference != "unknown":
        return reference
    if idx is not None:
        return f"Drill {idx}"
    return "Drill"


def _hole_edge_clearance(circle, bbox: dict) -> float:
    return min(
        (circle.center_x - circle.radius) - bbox["min_x"],
        bbox["max_x"] - (circle.center_x + circle.radius),
        (circle.center_y - circle.radius) - bbox["min_y"],
        bbox["max_y"] - (circle.center_y + circle.radius),
    )


def _drill_key(drill):
    reference = getattr(drill, "reference", "") or ""
    pad_name = getattr(drill, "pad_name", "") or ""
    if reference and reference != "unknown" and pad_name:
        return f"{reference}:{pad_name}"
    if reference and reference != "unknown":
        return reference
    return None


def _build_key_map(drills: list) -> dict[str, object] | None:
    key_map: dict[str, object] = {}
    reference_counts: dict[str, int] = {}
    for drill in drills:
        reference = getattr(drill, "reference", "") or ""
        if reference and reference != "unknown":
            reference_counts[reference] = reference_counts.get(reference, 0) + 1

    for drill in drills:
        reference = getattr(drill, "reference", "") or ""
        if reference and reference != "unknown" and reference_counts.get(reference, 0) == 1:
            key = reference
        else:
            key = _drill_key(drill)
        if not key or key in key_map:
            return None
        key_map[key] = drill
    return key_map


def _build_component_map(components: list) -> dict[str, object] | None:
    component_map: dict[str, object] = {}
    for component in components:
        reference = getattr(component, "reference", "") or ""
        if not reference or reference in component_map:
            return None
        component_map[reference] = component
    return component_map


def _pad_key(pad):
    reference = getattr(pad, "reference", "") or ""
    pad_name = getattr(pad, "pad_name", "") or ""
    if reference and reference != "unknown" and pad_name:
        return f"{reference}:{pad_name}"
    return None


def _build_pad_map(pads: list) -> dict[str, object] | None:
    pad_map: dict[str, object] = {}
    for pad in pads:
        key = _pad_key(pad)
        if not key:
            continue
        if key in pad_map:
            return None
        pad_map[key] = pad
    return pad_map if pad_map else None


def _iter_tracks(geometry: dict) -> list:
    return list(geometry.get("tracks") or [])


def _iter_pads(geometry: dict) -> list:
    return list(geometry.get("pads") or [])


def _iter_vias(geometry: dict) -> list:
    return list(geometry.get("vias") or [])


def _iter_nets(geometry: dict) -> list:
    return list(geometry.get("nets") or [])


def _distance(a, b) -> float:
    return math.hypot(a.center_x - b.center_x, a.center_y - b.center_y)


def _rotation_delta(a: float, b: float) -> float:
    delta = abs((a - b) % 360.0)
    return min(delta, 360.0 - delta)


def _track_edge_clearance(track, bbox: dict) -> float:
    min_x = min(track.start_x, track.end_x) - (track.width / 2.0)
    max_x = max(track.start_x, track.end_x) + (track.width / 2.0)
    min_y = min(track.start_y, track.end_y) - (track.width / 2.0)
    max_y = max(track.start_y, track.end_y) + (track.width / 2.0)
    return min(
        min_x - bbox["min_x"],
        bbox["max_x"] - max_x,
        min_y - bbox["min_y"],
        bbox["max_y"] - max_y,
    )


def _drill_spacing(a, b) -> float:
    return _distance(a, b) - a.radius - b.radius


def _component_spacing(a, b) -> float:
    return _distance(a, b)


def _point_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def _track_endpoints_delta(left, right) -> float:
    direct = max(
        _point_distance(left.start_x, left.start_y, right.start_x, right.start_y),
        _point_distance(left.end_x, left.end_y, right.end_x, right.end_y),
    )
    flipped = max(
        _point_distance(left.start_x, left.start_y, right.end_x, right.end_y),
        _point_distance(left.end_x, left.end_y, right.start_x, right.start_y),
    )
    return min(direct, flipped)


def _net_label(net_info: dict) -> str:
    name = (net_info.get("net_name") or "").strip()
    if name:
        return name
    return f"Net {net_info.get('net_id', 0)}"


def _net_compare_key(net_info: dict) -> str | None:
    name = (net_info.get("net_name") or "").strip()
    if name:
        return name
    net_id = int(net_info.get("net_id", 0) or 0)
    if net_id > 0:
        return f"NET:{net_id}"
    return None


def _pad_label(pad) -> str:
    reference = getattr(pad, "reference", "") or ""
    pad_name = getattr(pad, "pad_name", "") or ""
    if reference and reference != "unknown" and pad_name:
        return f"{reference}:{pad_name}"
    if reference and reference != "unknown":
        return reference
    return f"Pad {pad_name or '?'}"


def _build_net_connectivity(net_info: dict, pads: list, tracks: list, vias: list, *, attach_tolerance: float = 0.2):
    nodes: dict[str, dict] = {}
    adjacency: dict[str, set[str]] = {}

    def add_node(node_id: str, *, kind: str, x: float, y: float, radius: float, label: str):
        nodes[node_id] = {
            "kind": kind,
            "x": x,
            "y": y,
            "radius": max(radius, 0.0),
            "label": label,
        }
        adjacency[node_id] = set()

    def link(a: str, b: str):
        if a == b:
            return
        adjacency[a].add(b)
        adjacency[b].add(a)

    for idx, pad in enumerate(pads, start=1):
        add_node(
            f"pad:{idx}",
            kind="pad",
            x=pad.center_x,
            y=pad.center_y,
            radius=max(getattr(pad, "contact_radius", 0.0), 0.2),
            label=_pad_label(pad),
        )

    for idx, via in enumerate(vias, start=1):
        add_node(
            f"via:{idx}",
            kind="via",
            x=via.center_x,
            y=via.center_y,
            radius=max(via.size / 2.0, 0.2),
            label=f"Via {idx}",
        )

    for idx, track in enumerate(tracks, start=1):
        start_id = f"track:{idx}:start"
        end_id = f"track:{idx}:end"
        end_radius = max(track.width / 2.0, 0.1)
        add_node(
            start_id,
            kind="track_end",
            x=track.start_x,
            y=track.start_y,
            radius=end_radius,
            label=f"Track {idx} start",
        )
        add_node(
            end_id,
            kind="track_end",
            x=track.end_x,
            y=track.end_y,
            radius=end_radius,
            label=f"Track {idx} end",
        )
        link(start_id, end_id)

    node_ids = list(nodes)
    for left_index in range(len(node_ids) - 1):
        left_id = node_ids[left_index]
        left = nodes[left_id]
        for right_index in range(left_index + 1, len(node_ids)):
            right_id = node_ids[right_index]
            right = nodes[right_id]
            if _point_distance(left["x"], left["y"], right["x"], right["y"]) <= (
                left["radius"] + right["radius"] + attach_tolerance
            ):
                link(left_id, right_id)

    pad_ids = [node_id for node_id, node in nodes.items() if node["kind"] == "pad"]
    components: list[list[str]] = []
    visited: set[str] = set()

    for pad_id in pad_ids:
        if pad_id in visited:
            continue
        stack = [pad_id]
        group: list[str] = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            if nodes[current]["kind"] == "pad":
                group.append(nodes[current]["label"])
            stack.extend(neighbor for neighbor in adjacency[current] if neighbor not in visited)
        components.append(sorted(group))

    non_zone_routed = int(net_info.get("track_count", 0)) + int(net_info.get("via_count", 0))
    return {
        "pad_groups": [group for group in components if group],
        "component_count": len([group for group in components if group]),
        "non_zone_routed": non_zone_routed,
        "zone_count": int(net_info.get("zone_count", 0)),
    }


def _summarize(results: list[dict], geometry: dict | None = None) -> dict:
    n_pass = sum(1 for row in results if row["Status"] == "PASS")
    n_fail = sum(1 for row in results if row["Status"] == "FAIL")
    n_warn = sum(1 for row in results if row["Status"] == "WARN")

    summary = {
        "overall_status": "FAIL" if n_fail else ("WARN" if n_warn else "PASS"),
        "n_pass": n_pass,
        "n_fail": n_fail,
        "n_warn": n_warn,
    }

    if geometry is not None:
        bbox = geometry["bbox"]
        drills = _iter_drills(geometry)
        summary.update(
            {
                "bbox_width": bbox["width"],
                "bbox_height": bbox["height"],
                "n_drills": len(drills),
                "n_plated_drills": sum(1 for drill in drills if getattr(drill, "plated", False)),
                "n_mounting_holes": sum(1 for drill in drills if hasattr(drill, "plated") and not drill.plated),
                "n_components": len(geometry.get("components", [])),
                "n_tracks": len(_iter_tracks(geometry)),
                "n_signal_nets": int(geometry.get("stats", {}).get("n_signal_nets", 0)),
                "n_unrouted_signal_nets": int(geometry.get("stats", {}).get("n_unrouted_signal_nets", 0)),
            }
        )

    return summary


def calculate_validation_score(results: list[dict]) -> int:
    scored = [row for row in results if row.get("Status") in {"PASS", "FAIL", "WARN"}]
    if not scored:
        return 100
    passed = sum(1 for row in scored if row.get("Status") == "PASS")
    return int(round((passed / len(scored)) * 100))


def validate_cad_geometry(geometry: dict, rules: dict) -> tuple[list[dict], dict]:
    bbox = geometry["bbox"]
    drills = _iter_drills(geometry)
    results: list[dict] = []

    expected_drill_count = int(
        rules.get("expected_drill_count", rules.get("expected_hole_count", 0)) or 0
    )
    expected_plated_drill_count = int(rules.get("expected_plated_drill_count", 0) or 0)
    expected_mounting_hole_count = int(rules.get("expected_mounting_hole_count", 0) or 0)
    min_hole_diameter = float(rules.get("min_hole_diameter", 0.0) or 0.0)
    max_hole_diameter = float(rules.get("max_hole_diameter", 0.0) or 0.0)
    min_edge_clearance = float(rules.get("min_edge_clearance", 0.0) or 0.0)
    max_part_width = float(rules.get("max_part_width", 0.0) or 0.0)
    max_part_height = float(rules.get("max_part_height", 0.0) or 0.0)
    min_trace_width = float(rules.get("min_trace_width", 0.0) or 0.0)
    max_trace_width = float(rules.get("max_trace_width", 0.0) or 0.0)
    min_drill_spacing = float(rules.get("min_drill_spacing", 0.0) or 0.0)
    min_component_spacing = float(rules.get("min_component_spacing", 0.0) or 0.0)
    min_track_edge_clearance = float(rules.get("min_track_edge_clearance", 0.0) or 0.0)
    enable_deep_erc = bool(rules.get("enable_deep_erc", False))

    if expected_drill_count > 0:
        found = len(drills)
        results.append(
            _result(
                "Rules",
                "Total drill count",
                f"= {expected_drill_count}",
                str(found),
                _status(found == expected_drill_count),
                f"Expected {expected_drill_count} drills, found {found}.",
            )
        )

    if expected_plated_drill_count > 0:
        if not _has_plating_metadata(drills):
            results.append(
                _result(
                    "Rules",
                    "Plated drill count",
                    f"= {expected_plated_drill_count}",
                    "Unknown",
                    "WARN",
                    "This file does not carry plated-vs-NPTH drill metadata.",
                )
            )
        else:
            found = sum(1 for drill in drills if drill.plated)
            results.append(
                _result(
                    "Rules",
                    "Plated drill count",
                    f"= {expected_plated_drill_count}",
                    str(found),
                    _status(found == expected_plated_drill_count),
                    f"Expected {expected_plated_drill_count} plated drills, found {found}.",
                )
            )

    if expected_mounting_hole_count > 0:
        if not _has_plating_metadata(drills):
            results.append(
                _result(
                    "Rules",
                    "Mounting-hole count",
                    f"= {expected_mounting_hole_count}",
                    "Unknown",
                    "WARN",
                    "This file does not carry mounting-hole metadata.",
                )
            )
        else:
            found = sum(1 for drill in drills if not drill.plated)
            results.append(
                _result(
                    "Rules",
                    "Mounting-hole count",
                    f"= {expected_mounting_hole_count}",
                    str(found),
                    _status(found == expected_mounting_hole_count),
                    f"Expected {expected_mounting_hole_count} mounting holes, found {found}.",
                )
            )

    if min_hole_diameter > 0:
        if not drills:
            results.append(
                _result(
                    "Rules",
                    "Minimum drill diameter",
                    f">= {_fmt(min_hole_diameter)}",
                    "No drills found",
                    "WARN",
                    "No drill-like entities were detected in the uploaded file.",
                )
            )
        else:
            failures: list[dict] = []
            for idx, drill in enumerate(drills, start=1):
                label = _drill_label(drill, idx)
                found = drill.diameter
                if found < min_hole_diameter:
                    failures.append(
                        _result(
                            "Rules",
                            f"{label} diameter",
                            f">= {_fmt(min_hole_diameter)}",
                            _fmt(found),
                            "FAIL",
                            f"{label} must be at least {_fmt(min_hole_diameter)} mm; found {_fmt(found)} mm.",
                        )
                    )
            _append_bulk_results(
                results,
                failures,
                source="Rules",
                rule="Minimum drill diameter",
                required=f">= {_fmt(min_hole_diameter)}",
                total_checked=len(drills),
                pass_message=(
                    f"All {len(drills)} drills meet the minimum diameter of {_fmt(min_hole_diameter)} mm."
                ),
            )

    if max_hole_diameter > 0:
        if not drills:
            results.append(
                _result(
                    "Rules",
                    "Maximum drill diameter",
                    f"<= {_fmt(max_hole_diameter)}",
                    "No drills found",
                    "WARN",
                    "No drill-like entities were detected in the uploaded file.",
                )
            )
        else:
            failures = []
            for idx, drill in enumerate(drills, start=1):
                label = _drill_label(drill, idx)
                found = drill.diameter
                if found > max_hole_diameter:
                    failures.append(
                        _result(
                            "Rules",
                            f"{label} diameter",
                            f"<= {_fmt(max_hole_diameter)}",
                            _fmt(found),
                            "FAIL",
                            f"{label} must be at most {_fmt(max_hole_diameter)} mm; found {_fmt(found)} mm.",
                        )
                    )
            _append_bulk_results(
                results,
                failures,
                source="Rules",
                rule="Maximum drill diameter",
                required=f"<= {_fmt(max_hole_diameter)}",
                total_checked=len(drills),
                pass_message=(
                    f"All {len(drills)} drills stay within the maximum diameter of {_fmt(max_hole_diameter)} mm."
                ),
            )

    if min_edge_clearance > 0:
        if not drills:
            results.append(
                _result(
                    "Rules",
                    "Minimum drill-to-edge clearance",
                    f">= {_fmt(min_edge_clearance)}",
                    "No drills found",
                    "WARN",
                    "Drill-to-edge clearance cannot be measured because no drills were detected.",
                )
            )
        else:
            failures = []
            for idx, drill in enumerate(drills, start=1):
                label = _drill_label(drill, idx)
                found = _hole_edge_clearance(drill, bbox)
                if found < min_edge_clearance:
                    failures.append(
                        _result(
                            "Rules",
                            f"{label} edge clearance",
                            f">= {_fmt(min_edge_clearance)}",
                            _fmt(found),
                            "FAIL",
                            f"{label} needs at least {_fmt(min_edge_clearance)} mm edge clearance; found {_fmt(found)} mm.",
                        )
                    )
            _append_bulk_results(
                results,
                failures,
                source="Rules",
                rule="Minimum drill-to-edge clearance",
                required=f">= {_fmt(min_edge_clearance)}",
                total_checked=len(drills),
                pass_message=(
                    f"All {len(drills)} drills meet the minimum edge clearance of {_fmt(min_edge_clearance)} mm."
                ),
            )

    if max_part_width > 0:
        found = bbox["width"]
        results.append(
            _result(
                "Rules",
                "Board width",
                f"<= {_fmt(max_part_width)}",
                _fmt(found),
                _status(found <= max_part_width),
                f"Board width must be at most {_fmt(max_part_width)} mm; found {_fmt(found)} mm.",
            )
        )

    if max_part_height > 0:
        found = bbox["height"]
        results.append(
            _result(
                "Rules",
                "Board height",
                f"<= {_fmt(max_part_height)}",
                _fmt(found),
                _status(found <= max_part_height),
                f"Board height must be at most {_fmt(max_part_height)} mm; found {_fmt(found)} mm.",
            )
        )

    tracks = _iter_tracks(geometry)
    if min_trace_width > 0:
        if not tracks:
            results.append(
                _result(
                    "Rules",
                    "Minimum trace width",
                    f">= {_fmt(min_trace_width)}",
                    "No tracks found",
                    "WARN",
                    "This file did not provide copper track segments, so trace-width checks were skipped.",
                )
            )
        else:
            failures = []
            for idx, track in enumerate(tracks, start=1):
                if track.width < min_trace_width:
                    failures.append(
                        _result(
                            "Rules",
                            f"Track {idx} width",
                            f">= {_fmt(min_trace_width)}",
                            _fmt(track.width),
                            "FAIL",
                            (
                                f"Track {idx} on {track.layer} must be at least {_fmt(min_trace_width)} mm wide; "
                                f"found {_fmt(track.width)} mm."
                            ),
                        )
                    )
            _append_bulk_results(
                results,
                failures,
                source="Rules",
                rule="Minimum trace width",
                required=f">= {_fmt(min_trace_width)}",
                total_checked=len(tracks),
                pass_message=(
                    f"All {len(tracks)} tracks meet the minimum trace width of {_fmt(min_trace_width)} mm."
                ),
            )

    if max_trace_width > 0:
        if not tracks:
            results.append(
                _result(
                    "Rules",
                    "Maximum trace width",
                    f"<= {_fmt(max_trace_width)}",
                    "No tracks found",
                    "WARN",
                    "This file did not provide copper track segments, so trace-width checks were skipped.",
                )
            )
        else:
            failures = []
            for idx, track in enumerate(tracks, start=1):
                if track.width > max_trace_width:
                    failures.append(
                        _result(
                            "Rules",
                            f"Track {idx} width",
                            f"<= {_fmt(max_trace_width)}",
                            _fmt(track.width),
                            "FAIL",
                            (
                                f"Track {idx} on {track.layer} must be at most {_fmt(max_trace_width)} mm wide; "
                                f"found {_fmt(track.width)} mm."
                            ),
                        )
                    )
            _append_bulk_results(
                results,
                failures,
                source="Rules",
                rule="Maximum trace width",
                required=f"<= {_fmt(max_trace_width)}",
                total_checked=len(tracks),
                pass_message=(
                    f"All {len(tracks)} tracks stay within the maximum trace width of {_fmt(max_trace_width)} mm."
                ),
            )

    if min_drill_spacing > 0:
        if len(drills) < 2:
            results.append(
                _result(
                    "Rules",
                    "Minimum drill spacing",
                    f">= {_fmt(min_drill_spacing)}",
                    "Not enough drills",
                    "WARN",
                    "At least two drills are needed to measure drill-to-drill spacing.",
                )
            )
        else:
            failures = []
            pair_count = 0
            for left_index in range(len(drills) - 1):
                for right_index in range(left_index + 1, len(drills)):
                    pair_count += 1
                    left = drills[left_index]
                    right = drills[right_index]
                    found = _drill_spacing(left, right)
                    if found < min_drill_spacing:
                        left_label = _drill_label(left, left_index + 1)
                        right_label = _drill_label(right, right_index + 1)
                        failures.append(
                            _result(
                                "Rules",
                                f"Drill spacing {pair_count}",
                                f">= {_fmt(min_drill_spacing)}",
                                _fmt(found),
                                "FAIL",
                                (
                                    f"Spacing between {left_label} and {right_label} must be at least "
                                    f"{_fmt(min_drill_spacing)} mm; found {_fmt(found)} mm."
                                ),
                            )
                        )
            _append_bulk_results(
                results,
                failures,
                source="Rules",
                rule="Minimum drill spacing",
                required=f">= {_fmt(min_drill_spacing)}",
                total_checked=pair_count,
                pass_message=(
                    f"All {pair_count} drill pairs meet the minimum spacing of {_fmt(min_drill_spacing)} mm."
                ),
            )

    components = list(geometry.get("components") or [])
    if min_component_spacing > 0:
        if len(components) < 2:
            results.append(
                _result(
                    "Rules",
                    "Minimum component spacing",
                    f">= {_fmt(min_component_spacing)}",
                    "Not enough components",
                    "WARN",
                    "At least two components are needed to measure component spacing.",
                )
            )
        else:
            failures = []
            pair_count = 0
            for left_index in range(len(components) - 1):
                for right_index in range(left_index + 1, len(components)):
                    pair_count += 1
                    left = components[left_index]
                    right = components[right_index]
                    found = _component_spacing(left, right)
                    if found < min_component_spacing:
                        failures.append(
                            _result(
                                "Rules",
                                f"Component spacing {pair_count}",
                                f">= {_fmt(min_component_spacing)}",
                                _fmt(found),
                                "FAIL",
                                (
                                    f"Spacing between {left.reference} and {right.reference} must be at least "
                                    f"{_fmt(min_component_spacing)} mm; found {_fmt(found)} mm."
                                ),
                            )
                        )
            _append_bulk_results(
                results,
                failures,
                source="Rules",
                rule="Minimum component spacing",
                required=f">= {_fmt(min_component_spacing)}",
                total_checked=pair_count,
                pass_message=(
                    f"All {pair_count} component pairs meet the minimum spacing of {_fmt(min_component_spacing)} mm."
                ),
            )

    if min_track_edge_clearance > 0:
        if not tracks:
            results.append(
                _result(
                    "Rules",
                    "Minimum track-to-edge clearance",
                    f">= {_fmt(min_track_edge_clearance)}",
                    "No tracks found",
                    "WARN",
                    "This file did not provide copper track segments, so track-to-edge checks were skipped.",
                )
            )
        else:
            failures = []
            for idx, track in enumerate(tracks, start=1):
                found = _track_edge_clearance(track, bbox)
                if found < min_track_edge_clearance:
                    failures.append(
                        _result(
                            "Rules",
                            f"Track {idx} edge clearance",
                            f">= {_fmt(min_track_edge_clearance)}",
                            _fmt(found),
                            "FAIL",
                            (
                                f"Track {idx} on {track.layer} needs at least {_fmt(min_track_edge_clearance)} mm "
                                f"clearance from the board edge; found {_fmt(found)} mm."
                            ),
                        )
                    )
            _append_bulk_results(
                results,
                failures,
                source="Rules",
                rule="Minimum track-to-edge clearance",
                required=f">= {_fmt(min_track_edge_clearance)}",
                total_checked=len(tracks),
                pass_message=(
                    f"All {len(tracks)} tracks meet the minimum edge clearance of {_fmt(min_track_edge_clearance)} mm."
                ),
            )

    nets = _iter_nets(geometry)
    signal_nets = [net for net in nets if int(net.get("pad_count", 0)) >= 2]
    if nets:
        if not signal_nets:
            results.append(
                _result(
                    "Electrical",
                    "Basic routed-net check",
                    "Signal nets present",
                    "No multi-pad signal nets",
                    "WARN",
                    "No multi-pad routed nets were found, so the basic electrical routing check was skipped.",
                )
            )
        else:
            failures = []
            for net in signal_nets:
                copper_count = int(net.get("track_count", 0)) + int(net.get("via_count", 0))
                if copper_count <= 0:
                    net_name = _net_label(net)
                    pad_count = int(net.get("pad_count", 0))
                    failures.append(
                        _result(
                            "Electrical",
                            f"{net_name} routing",
                            "At least 1 track or via",
                            "No routed copper",
                            "FAIL",
                            (
                                f"{net_name} connects {pad_count} pads but has no track or via routing in the PCB file."
                            ),
                        )
                    )
            _append_bulk_results(
                results,
                failures,
                source="Electrical",
                rule="Basic routed-net check",
                required="Each multi-pad signal net has routed copper",
                total_checked=len(signal_nets),
                pass_message=(
                    f"All {len(signal_nets)} multi-pad signal nets have at least one routed copper feature."
                ),
            )

            if enable_deep_erc:
                pads = _iter_pads(geometry)
                vias = _iter_vias(geometry)
                continuity_failures = []
                continuity_checked = 0
                skipped_zone_nets = 0
                for net in signal_nets:
                    if int(net.get("zone_count", 0)) > 0:
                        skipped_zone_nets += 1
                        continue

                    net_id = int(net.get("net_id", 0))
                    net_pads = [pad for pad in pads if getattr(pad, "net_id", 0) == net_id]
                    net_tracks = [track for track in tracks if getattr(track, "net", 0) == net_id]
                    net_vias = [via for via in vias if getattr(via, "net_id", 0) == net_id]
                    continuity_checked += 1

                    connectivity = _build_net_connectivity(net, net_pads, net_tracks, net_vias)
                    if connectivity["component_count"] > 1:
                        group_parts = []
                        for idx, group in enumerate(connectivity["pad_groups"], start=1):
                            group_parts.append(f"group {idx}: {', '.join(group[:4])}")
                        continuity_failures.append(
                            _result(
                                "Electrical",
                                f"{_net_label(net)} continuity",
                                "All pads in one connected copper group",
                                f"{connectivity['component_count']} groups",
                                "FAIL",
                                (
                                    f"{_net_label(net)} is split into {connectivity['component_count']} disconnected pad groups; "
                                    + "; ".join(group_parts)
                                    + "."
                                ),
                            )
                        )

                if continuity_checked > 0:
                    _append_bulk_results(
                        results,
                        continuity_failures,
                        source="Electrical",
                        rule="Signal-net continuity",
                        required="All routed signal-net pads stay connected",
                        total_checked=continuity_checked,
                        pass_message=(
                            f"All {continuity_checked} checked signal nets kept their pads in one connected copper group."
                        ),
                    )

                if skipped_zone_nets > 0:
                    results.append(
                        _result(
                            "Electrical",
                            "Signal-net continuity",
                            "Full continuity check",
                            f"Skipped {skipped_zone_nets} zone-backed nets",
                            "WARN",
                            (
                                f"Skipped {skipped_zone_nets} signal nets that rely on copper zones because exact zone connectivity "
                                "is not modeled yet."
                            ),
                        )
                    )
    return results, _summarize(results, geometry)


def compare_geometry_to_reference(
    candidate: dict,
    reference: dict,
    *,
    board_tolerance: float = 0.1,
    drill_position_tolerance: float = 0.25,
    drill_diameter_tolerance: float = 0.05,
    component_position_tolerance: float = 0.25,
    component_rotation_tolerance: float = 1.0,
    pad_size_tolerance: float = 0.05,
    track_position_tolerance: float = 0.05,
    track_width_tolerance: float = 0.05,
) -> tuple[list[dict], dict]:
    results: list[dict] = []

    candidate_bbox = candidate["bbox"]
    reference_bbox = reference["bbox"]
    width_delta = abs(candidate_bbox["width"] - reference_bbox["width"])
    height_delta = abs(candidate_bbox["height"] - reference_bbox["height"])

    results.append(
        _result(
            "Reference",
            "Board width delta",
            f"<= {_fmt(board_tolerance)}",
            _fmt(width_delta),
            _status(width_delta <= board_tolerance),
            (
                f"Board width changed by {_fmt(width_delta)} mm. "
                f"Reference is {_fmt(reference_bbox['width'])} mm and candidate is {_fmt(candidate_bbox['width'])} mm."
            ),
        )
    )
    results.append(
        _result(
            "Reference",
            "Board height delta",
            f"<= {_fmt(board_tolerance)}",
            _fmt(height_delta),
            _status(height_delta <= board_tolerance),
            (
                f"Board height changed by {_fmt(height_delta)} mm. "
                f"Reference is {_fmt(reference_bbox['height'])} mm and candidate is {_fmt(candidate_bbox['height'])} mm."
            ),
        )
    )

    candidate_drills = _iter_drills(candidate)
    reference_drills = _iter_drills(reference)

    candidate_map = _build_key_map(candidate_drills)
    reference_map = _build_key_map(reference_drills)

    drill_issue_count = 0

    if candidate_map and reference_map:
        missing_keys = sorted(set(reference_map) - set(candidate_map))
        extra_keys = sorted(set(candidate_map) - set(reference_map))

        for key in missing_keys:
            drill_issue_count += 1
            ref_drill = reference_map[key]
            results.append(
                _result(
                    "Reference",
                    f"Missing drill {key}",
                    "Present in candidate",
                    "Missing",
                    "FAIL",
                    f"Reference drill {key} ({_fmt(ref_drill.diameter)} mm) is missing in the candidate board.",
                )
            )

        for key in extra_keys:
            drill_issue_count += 1
            cand_drill = candidate_map[key]
            results.append(
                _result(
                    "Reference",
                    f"Unexpected drill {key}",
                    "Not present in candidate",
                    f"{_fmt(cand_drill.diameter)} mm",
                    "FAIL",
                    f"Candidate board contains extra drill {key} with diameter {_fmt(cand_drill.diameter)} mm.",
                )
            )

        for key in sorted(set(reference_map) & set(candidate_map)):
            ref_drill = reference_map[key]
            cand_drill = candidate_map[key]
            diameter_delta = abs(cand_drill.diameter - ref_drill.diameter)
            if diameter_delta > drill_diameter_tolerance:
                drill_issue_count += 1
                results.append(
                    _result(
                        "Reference",
                        f"{key} diameter delta",
                        f"<= {_fmt(drill_diameter_tolerance)}",
                        _fmt(diameter_delta),
                        "FAIL",
                        (
                            f"{key} changed from {_fmt(ref_drill.diameter)} mm to "
                            f"{_fmt(cand_drill.diameter)} mm."
                        ),
                    )
                )

            position_delta = _distance(cand_drill, ref_drill)
            if position_delta > drill_position_tolerance:
                drill_issue_count += 1
                results.append(
                    _result(
                        "Reference",
                        f"{key} position delta",
                        f"<= {_fmt(drill_position_tolerance)}",
                        _fmt(position_delta),
                        "FAIL",
                        (
                            f"{key} moved by {_fmt(position_delta)} mm from the reference position."
                        ),
                    )
                )

            cand_plated = getattr(cand_drill, "plated", None)
            ref_plated = getattr(ref_drill, "plated", None)
            if cand_plated is not None and ref_plated is not None and cand_plated != ref_plated:
                drill_issue_count += 1
                results.append(
                    _result(
                        "Reference",
                        f"{key} drill type",
                        "Same as reference",
                        "Changed",
                        "FAIL",
                        f"{key} changed between plated and non-plated drill type.",
                    )
                )
    else:
        unmatched_candidate = set(range(len(candidate_drills)))
        for idx, ref_drill in enumerate(reference_drills, start=1):
            best_idx = None
            best_distance = None
            for cand_idx in unmatched_candidate:
                cand_drill = candidate_drills[cand_idx]
                distance = _distance(cand_drill, ref_drill)
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_idx = cand_idx

            if best_idx is None or best_distance is None or best_distance > drill_position_tolerance:
                drill_issue_count += 1
                results.append(
                    _result(
                        "Reference",
                        f"Missing drill {idx}",
                        "Present near reference position",
                        "Missing",
                        "FAIL",
                        f"Could not find a candidate drill near reference drill {idx}.",
                    )
                )
                continue

            unmatched_candidate.remove(best_idx)
            cand_drill = candidate_drills[best_idx]
            diameter_delta = abs(cand_drill.diameter - ref_drill.diameter)
            if diameter_delta > drill_diameter_tolerance:
                drill_issue_count += 1
                results.append(
                    _result(
                        "Reference",
                        f"Reference drill {idx} diameter delta",
                        f"<= {_fmt(drill_diameter_tolerance)}",
                        _fmt(diameter_delta),
                        "FAIL",
                        (
                            f"Reference drill {idx} changed from {_fmt(ref_drill.diameter)} mm to "
                            f"{_fmt(cand_drill.diameter)} mm."
                        ),
                    )
                )

        for extra_idx in sorted(unmatched_candidate):
            drill_issue_count += 1
            cand_drill = candidate_drills[extra_idx]
            results.append(
                _result(
                    "Reference",
                    f"Unexpected drill {extra_idx + 1}",
                    "No unmatched extra drills",
                    _fmt(cand_drill.diameter),
                    "FAIL",
                    "Candidate board contains an extra drill that is not in the reference layout.",
                )
            )

    if drill_issue_count == 0:
        results.append(
            _result(
                "Reference",
                "Drill comparison",
                "Same drill layout as reference",
                "Matched",
                "PASS",
                "No drill count, diameter, or position differences were found against the reference board.",
            )
        )

    candidate_components = list(candidate.get("components") or [])
    reference_components = list(reference.get("components") or [])
    component_issue_count = 0

    if candidate_components and reference_components:
        candidate_component_map = _build_component_map(candidate_components)
        reference_component_map = _build_component_map(reference_components)

        if candidate_component_map and reference_component_map:
            missing_components = sorted(set(reference_component_map) - set(candidate_component_map))
            extra_components = sorted(set(candidate_component_map) - set(reference_component_map))

            for reference_name in missing_components:
                component_issue_count += 1
                results.append(
                    _result(
                        "Reference",
                        f"Missing component {reference_name}",
                        "Present in candidate",
                        "Missing",
                        "FAIL",
                        f"Reference component {reference_name} is missing in the candidate PCB file.",
                    )
                )

            for reference_name in extra_components:
                component_issue_count += 1
                results.append(
                    _result(
                        "Reference",
                        f"Unexpected component {reference_name}",
                        "Not present in candidate",
                        "Extra",
                        "FAIL",
                        f"Candidate PCB file contains extra component {reference_name}.",
                    )
                )

            for reference_name in sorted(set(reference_component_map) & set(candidate_component_map)):
                reference_component = reference_component_map[reference_name]
                candidate_component = candidate_component_map[reference_name]

                position_delta = _distance(candidate_component, reference_component)
                if position_delta > component_position_tolerance:
                    component_issue_count += 1
                    results.append(
                        _result(
                            "Reference",
                            f"{reference_name} position delta",
                            f"<= {_fmt(component_position_tolerance)}",
                            _fmt(position_delta),
                            "FAIL",
                            (
                                f"{reference_name} moved by {_fmt(position_delta)} mm from the reference position."
                            ),
                        )
                    )

                rotation_delta = _rotation_delta(
                    candidate_component.rotation,
                    reference_component.rotation,
                )
                if rotation_delta > component_rotation_tolerance:
                    component_issue_count += 1
                    results.append(
                        _result(
                            "Reference",
                            f"{reference_name} rotation delta",
                            f"<= {_fmt(component_rotation_tolerance)}",
                            _fmt(rotation_delta),
                            "FAIL",
                            (
                                f"{reference_name} rotated by {_fmt(rotation_delta)} degrees from the reference orientation."
                            ),
                        )
                    )

        else:
            results.append(
                _result(
                    "Reference",
                    "Component comparison",
                    "Unique component references",
                    "Unavailable",
                    "WARN",
                    "Component comparison was skipped because the file did not provide unique component references.",
                )
            )
    elif candidate_components or reference_components:
        results.append(
            _result(
                "Reference",
                "Component comparison",
                "Component data in both files",
                "Partial",
                "WARN",
                "Component comparison was skipped because one of the files did not include component placement data.",
            )
        )

    if candidate_components and reference_components and component_issue_count == 0:
        results.append(
            _result(
                "Reference",
                "Component comparison",
                "Same component layout as reference",
                "Matched",
                "PASS",
                "No component count, position, or rotation differences were found against the reference PCB.",
            )
        )

    candidate_pads = [pad for pad in _iter_pads(candidate) if getattr(pad, "pad_type", "") != "np_thru_hole"]
    reference_pads = [pad for pad in _iter_pads(reference) if getattr(pad, "pad_type", "") != "np_thru_hole"]
    pad_issue_count = 0
    if candidate_pads and reference_pads:
        candidate_pad_map = _build_pad_map(candidate_pads)
        reference_pad_map = _build_pad_map(reference_pads)
        if candidate_pad_map and reference_pad_map:
            missing_pads = sorted(set(reference_pad_map) - set(candidate_pad_map))
            extra_pads = sorted(set(candidate_pad_map) - set(reference_pad_map))

            for key in missing_pads:
                pad_issue_count += 1
                results.append(
                    _result(
                        "Reference",
                        f"Missing pad {key}",
                        "Present in candidate",
                        "Missing",
                        "FAIL",
                        f"Reference pad {key} is missing in the candidate PCB file.",
                    )
                )

            for key in extra_pads:
                pad_issue_count += 1
                results.append(
                    _result(
                        "Reference",
                        f"Unexpected pad {key}",
                        "Not present in candidate",
                        "Extra",
                        "FAIL",
                        f"Candidate PCB file contains extra pad {key}.",
                    )
                )

            for key in sorted(set(reference_pad_map) & set(candidate_pad_map)):
                ref_pad = reference_pad_map[key]
                cand_pad = candidate_pad_map[key]
                size_x_delta = abs(getattr(cand_pad, "size_x", 0.0) - getattr(ref_pad, "size_x", 0.0))
                size_y_delta = abs(getattr(cand_pad, "size_y", 0.0) - getattr(ref_pad, "size_y", 0.0))
                if size_x_delta > pad_size_tolerance or size_y_delta > pad_size_tolerance:
                    pad_issue_count += 1
                    results.append(
                        _result(
                            "Reference",
                            f"{key} pad size delta",
                            f"<= {_fmt(pad_size_tolerance)}",
                            f"{_fmt(max(size_x_delta, size_y_delta))}",
                            "FAIL",
                            (
                                f"{key} pad size changed from {_fmt(getattr(ref_pad, 'size_x', 0.0))}x{_fmt(getattr(ref_pad, 'size_y', 0.0))} mm "
                                f"to {_fmt(getattr(cand_pad, 'size_x', 0.0))}x{_fmt(getattr(cand_pad, 'size_y', 0.0))} mm."
                            ),
                        )
                    )
        else:
            results.append(
                _result(
                    "Reference",
                    "Pad comparison",
                    "Unique pad references",
                    "Unavailable",
                    "WARN",
                    "Pad comparison was skipped because the file did not provide unique pad references.",
                )
            )

    if candidate_pads and reference_pads and pad_issue_count == 0:
        results.append(
            _result(
                "Reference",
                "Pad comparison",
                "Same pad geometry as reference",
                "Matched",
                "PASS",
                "No pad presence or pad-size differences were found against the reference PCB.",
            )
        )

    candidate_tracks = _iter_tracks(candidate)
    reference_tracks = _iter_tracks(reference)
    candidate_nets_for_tracks = _iter_nets(candidate)
    reference_nets_for_tracks = _iter_nets(reference)
    candidate_signal_net_ids = {
        int(net.get("net_id", 0) or 0)
        for net in candidate_nets_for_tracks
        if int(net.get("pad_count", 0)) >= 2
    }
    reference_signal_net_ids = {
        int(net.get("net_id", 0) or 0)
        for net in reference_nets_for_tracks
        if int(net.get("pad_count", 0)) >= 2
    }
    track_issue_count = 0
    if candidate_tracks and reference_tracks:
        unmatched_candidate = set(range(len(candidate_tracks)))
        matched_reference = 0

        for idx, ref_track in enumerate(reference_tracks, start=1):
            best_idx = None
            best_delta = None
            for cand_idx in unmatched_candidate:
                cand_track = candidate_tracks[cand_idx]
                if cand_track.layer != ref_track.layer:
                    continue
                delta = _track_endpoints_delta(cand_track, ref_track)
                if best_delta is None or delta < best_delta:
                    best_delta = delta
                    best_idx = cand_idx

            if best_idx is None or best_delta is None or best_delta > track_position_tolerance:
                track_issue_count += 1
                source = "Electrical" if int(getattr(ref_track, "net", 0) or 0) in reference_signal_net_ids else "Reference"
                results.append(
                    _result(
                        source,
                        f"Missing track {idx}",
                        "Track present near reference path",
                        "Missing",
                        "FAIL",
                        f"Reference track {idx} on {ref_track.layer} is missing or moved beyond {_fmt(track_position_tolerance)} mm.",
                    )
                )
                continue

            matched_reference += 1
            unmatched_candidate.remove(best_idx)
            cand_track = candidate_tracks[best_idx]
            width_delta = abs(cand_track.width - ref_track.width)
            if width_delta > track_width_tolerance:
                track_issue_count += 1
                results.append(
                    _result(
                        "Reference",
                        f"Track {idx} width delta",
                        f"<= {_fmt(track_width_tolerance)}",
                        _fmt(width_delta),
                        "FAIL",
                        (
                            f"Reference track {idx} on {ref_track.layer} changed from {_fmt(ref_track.width)} mm "
                            f"to {_fmt(cand_track.width)} mm."
                        ),
                    )
                )

        for extra_idx in sorted(unmatched_candidate):
            cand_track = candidate_tracks[extra_idx]
            track_issue_count += 1
            source = "Electrical" if int(getattr(cand_track, "net", 0) or 0) in candidate_signal_net_ids else "Reference"
            results.append(
                _result(
                    source,
                    f"Unexpected track {extra_idx + 1}",
                    "No unmatched extra copper segments",
                    f"{cand_track.layer} / {_fmt(cand_track.width)} mm",
                    "FAIL",
                    "Candidate board contains an extra copper track segment not found in the reference layout.",
                )
            )

        if matched_reference == 0:
            results.append(
                _result(
                    "Reference",
                    "Track comparison",
                    "Comparable copper paths",
                    "Unavailable",
                    "WARN",
                    "Track comparison found no close copper matches; this may happen if the candidate routing changed heavily.",
                )
            )

    if candidate_tracks and reference_tracks and track_issue_count == 0:
        results.append(
            _result(
                "Reference",
                "Track comparison",
                "Same track geometry as reference",
                "Matched",
                "PASS",
                "No track path or track-width differences were found against the reference PCB.",
            )
        )

    candidate_nets = _iter_nets(candidate)
    reference_nets = _iter_nets(reference)
    candidate_pads_all = _iter_pads(candidate)
    reference_pads_all = _iter_pads(reference)
    candidate_vias = _iter_vias(candidate)
    reference_vias = _iter_vias(reference)
    electrical_issue_count = 0

    if candidate_nets and reference_nets:
        candidate_net_map = {
            key: net for net in candidate_nets if (key := _net_compare_key(net)) is not None
        }
        reference_net_map = {
            key: net for net in reference_nets if (key := _net_compare_key(net)) is not None
        }

        for key in sorted(set(reference_net_map) & set(candidate_net_map)):
            reference_net = reference_net_map[key]
            candidate_net = candidate_net_map[key]

            if int(reference_net.get("pad_count", 0)) < 2:
                continue

            ref_name = _net_label(reference_net)
            reference_has_copper = (
                int(reference_net.get("track_count", 0))
                + int(reference_net.get("via_count", 0))
                + int(reference_net.get("zone_count", 0))
            ) > 0
            candidate_has_copper = (
                int(candidate_net.get("track_count", 0))
                + int(candidate_net.get("via_count", 0))
                + int(candidate_net.get("zone_count", 0))
            ) > 0

            if reference_has_copper and not candidate_has_copper:
                electrical_issue_count += 1
                results.append(
                    _result(
                        "Electrical",
                        f"{ref_name} routed copper",
                        "Routed copper present",
                        "No routed copper",
                        "FAIL",
                        f"{ref_name} had routed copper in the reference board but none was found in the candidate board.",
                    )
                )
                continue

            if int(reference_net.get("zone_count", 0)) > 0 or int(candidate_net.get("zone_count", 0)) > 0:
                continue

            ref_net_id = int(reference_net.get("net_id", 0) or 0)
            cand_net_id = int(candidate_net.get("net_id", 0) or 0)
            ref_net_pads = [pad for pad in reference_pads_all if getattr(pad, "net_id", 0) == ref_net_id]
            cand_net_pads = [pad for pad in candidate_pads_all if getattr(pad, "net_id", 0) == cand_net_id]
            ref_net_tracks = [track for track in reference_tracks if getattr(track, "net", 0) == ref_net_id]
            cand_net_tracks = [track for track in candidate_tracks if getattr(track, "net", 0) == cand_net_id]
            ref_net_vias = [via for via in reference_vias if getattr(via, "net_id", 0) == ref_net_id]
            cand_net_vias = [via for via in candidate_vias if getattr(via, "net_id", 0) == cand_net_id]

            ref_connectivity = _build_net_connectivity(reference_net, ref_net_pads, ref_net_tracks, ref_net_vias)
            cand_connectivity = _build_net_connectivity(candidate_net, cand_net_pads, cand_net_tracks, cand_net_vias)

            ref_groups = int(ref_connectivity.get("component_count", 0))
            cand_groups = int(cand_connectivity.get("component_count", 0))
            if ref_groups <= 1 and cand_groups > 1:
                electrical_issue_count += 1
                results.append(
                    _result(
                        "Electrical",
                        f"{ref_name} continuity against reference",
                        "One connected pad group",
                        f"{cand_groups} groups",
                        "FAIL",
                        f"{ref_name} was electrically continuous in the reference board but is split into {cand_groups} disconnected pad groups in the candidate board.",
                    )
                )

    if candidate_nets and reference_nets and electrical_issue_count == 0:
        results.append(
            _result(
                "Electrical",
                "Reference electrical comparison",
                "Signal-net behavior matches reference",
                "Matched",
                "PASS",
                "No routed-copper loss or continuity regressions were found against the reference board.",
            )
        )

    return results, _summarize(results)
