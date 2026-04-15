"""
kicad_parser.py - lightweight KiCad .kicad_pcb geometry parser

This parser extracts:
  - board outline bbox from Edge.Cuts gr_line segments
  - drilled holes from thru_hole / np_thru_hole pads
  - pad net assignments and via net assignments
  - copper track segments and widths from segment records

The goal is exact rule validation for board size and drill properties.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re


MODULE_RE = re.compile(r"^\s*\((?:module|footprint)\s+(.+?)\s+\(layer")
MODULE_LAYER_RE = re.compile(r"\(layer\s+([^)]+)\)")
AT_RE = re.compile(r"^\s*\(at\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)(?:\s+(-?\d+(?:\.\d+)?))?\)")
FP_REF_RE = re.compile(r"^\s*\(fp_text reference\s+([^\s)]+)")
PROPERTY_REF_RE = re.compile(r'^\s*\(property\s+"Reference"\s+"([^"]*)"')
PAD_RE = re.compile(r"^\s*\(pad\s+([^\s]+)\s+(thru_hole|np_thru_hole|smd)\s+([^\s]+)")
PAD_AT_RE = re.compile(r"\(at\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)(?:\s+(-?\d+(?:\.\d+)?))?\)")
PAD_SIZE_RE = re.compile(r"\(size\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\)")
DRILL_RE = re.compile(r"\(drill\s+(?:oval\s+)?(-?\d+(?:\.\d+)?)(?:\s+(-?\d+(?:\.\d+)?))?")
PAD_NET_RE = re.compile(r'\(net\s+(?:(\d+)(?:\s+"([^"]*)")?|"([^"]*)")\)')
EDGE_LINE_RE = re.compile(
    r"^\s*\(gr_line\s+\(start\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\)\s+"
    r"\(end\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\)\s+\(layer Edge\.Cuts\)"
)
SEGMENT_RE = re.compile(
    r"^\s*\(segment\s+\(start\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\)\s+"
    r"\(end\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\)\s+"
    r"\(width\s+(-?\d+(?:\.\d+)?)\)\s+\(layer\s+([^)]+)\)\s+\(net\s+(\d+)\)\)"
)
TRACE_MIN_RE = re.compile(r"^\s*\(trace_min\s+(-?\d+(?:\.\d+)?)\)")
TRACE_CLEARANCE_RE = re.compile(r"^\s*\(trace_clearance\s+(-?\d+(?:\.\d+)?)\)")
VIA_DRILL_RE = re.compile(r"^\s*\(via_drill\s+(-?\d+(?:\.\d+)?)\)")
NET_DEF_RE = re.compile(r'^\s*\(net\s+(\d+)\s+"([^"]*)"\)')
VIA_RE = re.compile(
    r"^\s*\(via\s+\(at\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\)\s+"
    r"\(size\s+(-?\d+(?:\.\d+)?)\)\s+\(drill\s+(-?\d+(?:\.\d+)?)\)\s+"
    r"\(layers\s+([^)]+)\)\s+\(net\s+(\d+)\)\)"
)
ZONE_RE = re.compile(r'^\s*\(zone\s+\(net\s+(\d+)\)\s+\(net_name\s+"([^"]*)"\)\s+\(layer\s+([^)]+)\)')
START_ANY_RE = re.compile(r"\(start\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\)")
END_ANY_RE = re.compile(r"\(end\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\)")
WIDTH_ANY_RE = re.compile(r"\(width\s+(-?\d+(?:\.\d+)?)\)")
LAYER_ANY_RE = re.compile(r'\(layer\s+"?([^")]+)"?\)')
NET_ANY_RE = re.compile(r'\(net\s+(?:(\d+)|"([^"]*)")')
AT_ANY_RE = re.compile(r"\(at\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\)")
SIZE_ANY_RE = re.compile(r"\(size\s+(-?\d+(?:\.\d+)?)\)")
DRILL_ANY_RE = re.compile(r"\(drill\s+(-?\d+(?:\.\d+)?)\)")
LAYERS_ANY_RE = re.compile(r"\(layers\s+([^)]+)\)")


@dataclass
class DrillHole:
    center_x: float
    center_y: float
    drill_x: float
    drill_y: float
    plated: bool
    reference: str
    module_name: str
    pad_name: str

    @property
    def diameter(self) -> float:
        return max(self.drill_x, self.drill_y)

    @property
    def radius(self) -> float:
        return self.diameter / 2.0


@dataclass
class ComponentPlacement:
    reference: str
    module_name: str
    center_x: float
    center_y: float
    rotation: float


@dataclass
class TrackSegment:
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    width: float
    layer: str
    net: int

    @property
    def length(self) -> float:
        return math.hypot(self.end_x - self.start_x, self.end_y - self.start_y)


@dataclass
class PadConnection:
    reference: str
    module_name: str
    pad_name: str
    pad_type: str
    center_x: float
    center_y: float
    size_x: float
    size_y: float
    net_id: int
    net_name: str

    @property
    def contact_radius(self) -> float:
        return max(self.size_x, self.size_y) / 2.0


@dataclass
class ViaPoint:
    center_x: float
    center_y: float
    size: float
    drill: float
    layers: str
    net_id: int
    net_name: str


def _update_bbox(bbox: list[float] | None, x: float, y: float) -> list[float]:
    if bbox is None:
        return [x, y, x, y]
    bbox[0] = min(bbox[0], x)
    bbox[1] = min(bbox[1], y)
    bbox[2] = max(bbox[2], x)
    bbox[3] = max(bbox[3], y)
    return bbox


def _rotate(x: float, y: float, degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    cos_v = math.cos(radians)
    sin_v = math.sin(radians)
    return (x * cos_v - y * sin_v, x * sin_v + y * cos_v)


def _iter_module_blocks(text: str):
    current: list[str] = []
    balance = 0
    in_module = False

    for line in text.splitlines():
        stripped = line.lstrip()
        if not in_module and (stripped.startswith("(module ") or stripped.startswith("(footprint ")):
            in_module = True
            current = [line]
            balance = line.count("(") - line.count(")")
            if balance <= 0:
                yield current
                current = []
                balance = 0
                in_module = False
            continue

        if in_module:
            current.append(line)
            balance += line.count("(") - line.count(")")
            if balance <= 0:
                yield current
                current = []
                balance = 0
                in_module = False


def _iter_nested_blocks(lines: list[str], prefixes: tuple[str, ...]):
    current: list[str] = []
    balance = 0
    in_block = False

    for line in lines:
        stripped = line.lstrip()
        if not in_block and any(stripped.startswith(f"({prefix}") for prefix in prefixes):
            in_block = True
            current = [line]
            balance = line.count("(") - line.count(")")
            if balance <= 0:
                yield current
                current = []
                balance = 0
                in_block = False
            continue

        if in_block:
            current.append(line)
            balance += line.count("(") - line.count(")")
            if balance <= 0:
                yield current
                current = []
                balance = 0
                in_block = False


def _resolve_net_ref(
    numeric_id: str | None,
    numeric_name: str | None,
    quoted_name: str | None,
    net_names: dict[int, str],
    synthetic_net_ids: dict[str, int],
) -> tuple[int, str]:
    if numeric_id is not None:
        net_id = int(numeric_id)
        net_name = (numeric_name or "").strip() or net_names.get(net_id, "")
        return net_id, net_name

    net_name = (quoted_name or "").strip()
    if not net_name:
        return 0, ""

    if net_name not in synthetic_net_ids:
        synthetic_net_ids[net_name] = 100000 + len(synthetic_net_ids) + 1
    return synthetic_net_ids[net_name], net_name


def _parse_module_block(
    lines: list[str], net_names: dict[int, str], synthetic_net_ids: dict[str, int]
) -> tuple[list[DrillHole], ComponentPlacement | None, list[PadConnection]]:
    header = lines[0]
    name_match = MODULE_RE.match(header)
    module_name = name_match.group(1) if name_match else "unknown"
    layer_match = MODULE_LAYER_RE.search(header)
    module_layer = (layer_match.group(1) if layer_match else "").strip()

    module_x = 0.0
    module_y = 0.0
    module_rot = 0.0
    reference = module_name
    seen_at = False
    drills: list[DrillHole] = []
    pads: list[PadConnection] = []

    for line in lines[1:]:
        if not seen_at:
            at_match = AT_RE.match(line)
            if at_match:
                module_x = float(at_match.group(1))
                module_y = float(at_match.group(2))
                module_rot = float(at_match.group(3) or 0.0)
                seen_at = True
                continue

        ref_match = FP_REF_RE.match(line)
        if ref_match:
            reference = ref_match.group(1).strip('"')
            continue

        property_ref_match = PROPERTY_REF_RE.match(line)
        if property_ref_match and property_ref_match.group(1).strip():
            reference = property_ref_match.group(1).strip()
            continue

        if not module_layer:
            layer_inline = MODULE_LAYER_RE.search(line)
            if layer_inline:
                module_layer = layer_inline.group(1).strip().strip('"')

    mirrored = module_layer.startswith("B.")

    for pad_block in _iter_nested_blocks(lines[1:], ("pad ",)):
        header_line = pad_block[0]
        pad_match = PAD_RE.match(header_line)
        if not pad_match:
            continue

        pad_name, pad_type, _shape = pad_match.groups()
        pad_name = pad_name.strip('"')
        pad_text = "\n".join(pad_block)
        at_match = PAD_AT_RE.search(pad_text)
        if not at_match:
            continue

        net_match = PAD_NET_RE.search(pad_text)
        if net_match:
            net_id, net_name = _resolve_net_ref(
                net_match.group(1),
                net_match.group(2),
                net_match.group(3),
                net_names,
                synthetic_net_ids,
            )
        else:
            net_id, net_name = 0, ""
        size_match = PAD_SIZE_RE.search(pad_text)
        size_x = abs(float(size_match.group(1))) if size_match else 0.0
        size_y = abs(float(size_match.group(2))) if size_match else size_x

        local_x = float(at_match.group(1))
        local_y = float(at_match.group(2))
        if mirrored:
            local_x = -local_x
        rot_x, rot_y = _rotate(local_x, local_y, module_rot)
        pads.append(
            PadConnection(
                reference=reference,
                module_name=module_name,
                pad_name=pad_name,
                pad_type=pad_type,
                center_x=module_x + rot_x,
                center_y=module_y + rot_y,
                size_x=size_x,
                size_y=size_y,
                net_id=net_id,
                net_name=net_name,
            )
        )

        if pad_type not in {"thru_hole", "np_thru_hole"}:
            continue

        drill_match = DRILL_RE.search(pad_text)
        if not drill_match:
            continue

        drill_x = float(drill_match.group(1))
        drill_y = float(drill_match.group(2) or drill_match.group(1))
        drills.append(
            DrillHole(
                center_x=module_x + rot_x,
                center_y=module_y + rot_y,
                drill_x=abs(drill_x),
                drill_y=abs(drill_y),
                plated=(pad_type == "thru_hole"),
                reference=reference,
                module_name=module_name,
                pad_name=pad_name,
            )
        )

    component = None
    clean_reference = reference.strip().strip('"')
    if clean_reference and clean_reference not in {"unknown", "~"}:
        component = ComponentPlacement(
            reference=clean_reference,
            module_name=module_name,
            center_x=module_x,
            center_y=module_y,
            rotation=module_rot,
        )

    return drills, component, pads


def parse_kicad_pcb_text(text: str) -> dict:
    bbox = None
    tracks: list[TrackSegment] = []
    vias: list[ViaPoint] = []
    pads: list[PadConnection] = []
    setup_trace_min = 0.0
    setup_trace_clearance = 0.0
    setup_via_drill = 0.0
    net_names: dict[int, str] = {}
    synthetic_net_ids: dict[str, int] = {}
    zone_counts: dict[int, int] = {}
    for line in text.splitlines():
        net_def_match = NET_DEF_RE.match(line)
        if net_def_match:
            net_names[int(net_def_match.group(1))] = net_def_match.group(2)
            continue

        zone_match = ZONE_RE.match(line)
        if zone_match:
            net_id = int(zone_match.group(1))
            zone_counts[net_id] = zone_counts.get(net_id, 0) + 1
            if zone_match.group(2):
                net_names.setdefault(net_id, zone_match.group(2))
            continue

        trace_min_match = TRACE_MIN_RE.match(line)
        if trace_min_match:
            setup_trace_min = float(trace_min_match.group(1))
            continue

        trace_clearance_match = TRACE_CLEARANCE_RE.match(line)
        if trace_clearance_match:
            setup_trace_clearance = float(trace_clearance_match.group(1))
            continue

        via_drill_match = VIA_DRILL_RE.match(line)
        if via_drill_match:
            setup_via_drill = float(via_drill_match.group(1))
            continue

    for block in _iter_nested_blocks(text.splitlines(), ("gr_line", "segment", "via")):
        header = block[0].lstrip()
        block_text = "\n".join(block)

        if header.startswith("(gr_line"):
            line_match = EDGE_LINE_RE.match(header)
            if line_match:
                x1, y1, x2, y2 = map(float, line_match.groups())
                bbox = _update_bbox(bbox, x1, y1)
                bbox = _update_bbox(bbox, x2, y2)
                continue

            layer_match = LAYER_ANY_RE.search(block_text)
            start_match = START_ANY_RE.search(block_text)
            end_match = END_ANY_RE.search(block_text)
            if (
                layer_match
                and start_match
                and end_match
                and layer_match.group(1).strip() == "Edge.Cuts"
            ):
                x1, y1 = map(float, start_match.groups())
                x2, y2 = map(float, end_match.groups())
                bbox = _update_bbox(bbox, x1, y1)
                bbox = _update_bbox(bbox, x2, y2)
                continue

        if header.startswith("(segment"):
            segment_match = SEGMENT_RE.match(header)
            if segment_match:
                x1, y1, x2, y2, width, layer, net = segment_match.groups()
                tracks.append(
                    TrackSegment(
                        start_x=float(x1),
                        start_y=float(y1),
                        end_x=float(x2),
                        end_y=float(y2),
                        width=abs(float(width)),
                        layer=layer.strip().strip('"'),
                        net=int(net),
                    )
                )
                continue

            start_match = START_ANY_RE.search(block_text)
            end_match = END_ANY_RE.search(block_text)
            width_match = WIDTH_ANY_RE.search(block_text)
            layer_match = LAYER_ANY_RE.search(block_text)
            net_match = NET_ANY_RE.search(block_text)
            if start_match and end_match and width_match and layer_match and net_match:
                x1, y1 = map(float, start_match.groups())
                x2, y2 = map(float, end_match.groups())
                net_id, net_name = _resolve_net_ref(
                    net_match.group(1),
                    None,
                    net_match.group(2),
                    net_names,
                    synthetic_net_ids,
                )
                tracks.append(
                    TrackSegment(
                        start_x=x1,
                        start_y=y1,
                        end_x=x2,
                        end_y=y2,
                        width=abs(float(width_match.group(1))),
                        layer=layer_match.group(1).strip(),
                        net=net_id,
                    )
                )
                if net_name and net_id > 0:
                    net_names.setdefault(net_id, net_name)
                continue

        if header.startswith("(via"):
            via_match = VIA_RE.match(header)
            if via_match:
                x, y, size, drill, layers, net_id = via_match.groups()
                net_id_int = int(net_id)
                vias.append(
                    ViaPoint(
                        center_x=float(x),
                        center_y=float(y),
                        size=abs(float(size)),
                        drill=abs(float(drill)),
                        layers=layers.strip(),
                        net_id=net_id_int,
                        net_name=net_names.get(net_id_int, ""),
                    )
                )
                continue

            at_match = AT_ANY_RE.search(block_text)
            size_match = SIZE_ANY_RE.search(block_text)
            drill_match = DRILL_ANY_RE.search(block_text)
            layers_match = LAYERS_ANY_RE.search(block_text)
            net_match = NET_ANY_RE.search(block_text)
            if at_match and size_match and drill_match and layers_match and net_match:
                x, y = map(float, at_match.groups())
                net_id_int, net_name = _resolve_net_ref(
                    net_match.group(1),
                    None,
                    net_match.group(2),
                    net_names,
                    synthetic_net_ids,
                )
                vias.append(
                    ViaPoint(
                        center_x=x,
                        center_y=y,
                        size=abs(float(size_match.group(1))),
                        drill=abs(float(drill_match.group(1))),
                        layers=layers_match.group(1).strip(),
                        net_id=net_id_int,
                        net_name=net_name or net_names.get(net_id_int, ""),
                    )
                )
                if net_name and net_id_int > 0:
                    net_names.setdefault(net_id_int, net_name)

    if bbox is None:
        raise ValueError("No Edge.Cuts board outline found in the KiCad PCB file.")

    drills: list[DrillHole] = []
    components: list[ComponentPlacement] = []
    for block in _iter_module_blocks(text):
        block_drills, component, block_pads = _parse_module_block(block, net_names, synthetic_net_ids)
        drills.extend(block_drills)
        pads.extend(block_pads)
        if component is not None:
            components.append(component)

    min_x, min_y, max_x, max_y = bbox
    plated_count = sum(1 for drill in drills if drill.plated)
    npth_count = sum(1 for drill in drills if not drill.plated)
    min_drill = min((drill.diameter for drill in drills), default=0.0)
    max_drill = max((drill.diameter for drill in drills), default=0.0)
    min_track_width = min((track.width for track in tracks), default=0.0)
    max_track_width = max((track.width for track in tracks), default=0.0)
    total_track_length = sum(track.length for track in tracks)

    net_index: dict[int, dict] = {}

    def _ensure_net(net_id: int) -> dict:
        if net_id not in net_index:
            net_index[net_id] = {
                "net_id": net_id,
                "net_name": net_names.get(net_id, ""),
                "pad_count": 0,
                "track_count": 0,
                "via_count": 0,
                "zone_count": zone_counts.get(net_id, 0),
                "component_refs": set(),
            }
        return net_index[net_id]

    for pad in pads:
        if pad.net_id <= 0:
            continue
        item = _ensure_net(pad.net_id)
        item["pad_count"] += 1
        item["component_refs"].add(pad.reference)
        if not item["net_name"] and pad.net_name:
            item["net_name"] = pad.net_name

    for track in tracks:
        if track.net <= 0:
            continue
        item = _ensure_net(track.net)
        item["track_count"] += 1

    for via in vias:
        if via.net_id <= 0:
            continue
        item = _ensure_net(via.net_id)
        item["via_count"] += 1
        if not item["net_name"] and via.net_name:
            item["net_name"] = via.net_name

    for net_id, zone_count in zone_counts.items():
        item = _ensure_net(net_id)
        item["zone_count"] = zone_count

    net_records = []
    signal_nets = 0
    routed_signal_nets = 0
    unrouted_signal_nets = 0
    for net_id in sorted(net_index):
        item = net_index[net_id]
        item["component_refs"] = sorted(ref for ref in item["component_refs"] if ref and ref != "unknown")
        if item["pad_count"] >= 2:
            signal_nets += 1
            if item["track_count"] + item["via_count"] + int(item.get("zone_count", 0)) > 0:
                routed_signal_nets += 1
            else:
                unrouted_signal_nets += 1
        net_records.append(item)

    return {
        "source_type": "kicad_pcb",
        "circles": drills,
        "drills": drills,
        "pads": pads,
        "components": components,
        "tracks": tracks,
        "vias": vias,
        "nets": net_records,
        "bbox": {
            "min_x": min_x,
            "min_y": min_y,
            "max_x": max_x,
            "max_y": max_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
        },
        "stats": {
            "n_drills": len(drills),
            "n_plated_drills": plated_count,
            "n_mounting_holes": npth_count,
            "min_drill_diameter": min_drill,
            "max_drill_diameter": max_drill,
            "n_components": len(components),
            "n_tracks": len(tracks),
            "n_vias": len(vias),
            "n_pads": len(pads),
            "n_nets": len(net_records),
            "n_signal_nets": signal_nets,
            "n_routed_signal_nets": routed_signal_nets,
            "n_unrouted_signal_nets": unrouted_signal_nets,
            "min_track_width": min_track_width,
            "max_track_width": max_track_width,
            "total_track_length": total_track_length,
            "setup_trace_min": setup_trace_min,
            "setup_trace_clearance": setup_trace_clearance,
            "setup_via_drill": setup_via_drill,
        },
    }


def parse_kicad_pcb_bytes(payload: bytes) -> dict:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        text = payload.decode("latin-1")
    return parse_kicad_pcb_text(text)
