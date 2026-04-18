"""
Shared validation service helpers for the API-backed frontend.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image

from cad_parser import parse_dxf_bytes
from cad_rules import calculate_validation_score, compare_geometry_to_reference, validate_cad_geometry
from kicad_parser import parse_kicad_pcb_bytes
from llm_assistant import (
    ai_available,
    default_model_for_available_provider,
    generate_validation_guidance,
    get_available_provider,
)
from pcb_report_generator import build_pcb_preview, generate_pcb_validation_report


DEMO_REFERENCE_PATH = Path("demo_boards/triac_reference.kicad_pcb")


def parse_geometry(name: str, payload: bytes) -> tuple[dict, str]:
    lower_name = name.lower()
    if lower_name.endswith(".kicad_pcb"):
        return parse_kicad_pcb_bytes(payload), ".kicad_pcb"
    if lower_name.endswith(".dxf"):
        return parse_dxf_bytes(payload), ".dxf"
    raise ValueError("Upload a .kicad_pcb or .dxf file.")


def load_demo_reference() -> tuple[dict, str] | None:
    if not DEMO_REFERENCE_PATH.is_file():
        return None
    payload = DEMO_REFERENCE_PATH.read_bytes()
    geometry, extension = parse_geometry(DEMO_REFERENCE_PATH.name, payload)
    return geometry, extension


def default_rules(sample_geometry: dict | None = None) -> dict:
    if sample_geometry is not None:
        stats = sample_geometry.get("stats", {})
        bbox = sample_geometry.get("bbox", {})
        return {
            "expected_drill_count": int(stats.get("n_drills", 0)),
            "expected_plated_drill_count": int(stats.get("n_plated_drills", 0)),
            "expected_mounting_hole_count": int(stats.get("n_mounting_holes", 0)),
            "min_hole_diameter": float(stats.get("min_drill_diameter", 0.0)),
            "max_hole_diameter": float(stats.get("max_drill_diameter", 0.0)),
            "min_trace_width": float(stats.get("setup_trace_min") or stats.get("min_track_width", 0.0)),
            "max_trace_width": 0.0,
            "min_edge_clearance": 0.0,
            "min_drill_spacing": 0.0,
            "min_component_spacing": 0.0,
            "min_track_edge_clearance": float(stats.get("setup_trace_clearance", 0.0)),
            "max_part_width": float(bbox.get("width", 0.0)),
            "max_part_height": float(bbox.get("height", 0.0)),
            "enable_deep_erc": False,
        }

    return {
        "expected_drill_count": 0,
        "expected_plated_drill_count": 0,
        "expected_mounting_hole_count": 0,
        "min_hole_diameter": 0.0,
        "max_hole_diameter": 0.0,
        "min_trace_width": 0.0,
        "max_trace_width": 0.0,
        "min_edge_clearance": 0.0,
        "min_drill_spacing": 0.0,
        "min_component_spacing": 0.0,
        "min_track_edge_clearance": 0.0,
        "max_part_width": 0.0,
        "max_part_height": 0.0,
        "enable_deep_erc": False,
    }


def combined_summary(*summaries: dict | None) -> dict:
    statuses = [summary["overall_status"] for summary in summaries if summary]
    n_pass = sum(summary.get("n_pass", 0) for summary in summaries if summary)
    n_fail = sum(summary.get("n_fail", 0) for summary in summaries if summary)
    n_warn = sum(summary.get("n_warn", 0) for summary in summaries if summary)

    if "FAIL" in statuses:
        overall = "FAIL"
    elif "WARN" in statuses:
        overall = "WARN"
    else:
        overall = "PASS"

    return {
        "overall_status": overall,
        "n_pass": n_pass,
        "n_fail": n_fail,
        "n_warn": n_warn,
    }


def ai_metrics(geometry: dict) -> dict:
    stats = geometry.get("stats", {})
    bbox = geometry.get("bbox", {})
    return {
        "board_width_mm": round(float(bbox.get("width", 0.0)), 3),
        "board_height_mm": round(float(bbox.get("height", 0.0)), 3),
        "total_drills": int(stats.get("n_drills", 0)),
        "plated_drills": int(stats.get("n_plated_drills", 0)),
        "mounting_holes": int(stats.get("n_mounting_holes", 0)),
        "components": int(stats.get("n_components", 0)),
        "tracks": int(stats.get("n_tracks", 0)),
        "signal_nets": int(stats.get("n_signal_nets", 0)),
        "unrouted_signal_nets": int(stats.get("n_unrouted_signal_nets", 0)),
        "min_track_width_mm": round(float(stats.get("min_track_width", 0.0)), 3),
        "kicad_trace_min_mm": round(float(stats.get("setup_trace_min", 0.0)), 4),
        "kicad_trace_clearance_mm": round(float(stats.get("setup_trace_clearance", 0.0)), 4),
    }


def metrics_summary(geometry: dict) -> dict:
    bbox = geometry.get("bbox", {})
    stats = geometry.get("stats", {})
    return {
        "board_width_mm": round(float(bbox.get("width", 0.0)), 3),
        "board_height_mm": round(float(bbox.get("height", 0.0)), 3),
        "total_drills": int(stats.get("n_drills", stats.get("n_circles", 0))),
        "components": int(stats.get("n_components", 0)),
        "plated_drills": int(stats.get("n_plated_drills", 0)),
        "min_drill_mm": round(float(stats.get("min_drill_diameter", 0.0)), 3),
        "max_drill_mm": round(float(stats.get("max_drill_diameter", 0.0)), 3),
        "mounting_holes": int(stats.get("n_mounting_holes", 0)),
        "tracks": int(stats.get("n_tracks", 0)),
        "signal_nets": int(stats.get("n_signal_nets", 0)),
        "unrouted_signal_nets": int(stats.get("n_unrouted_signal_nets", 0)),
        "min_track_width_mm": round(float(stats.get("min_track_width", 0.0)), 3),
        "kicad_trace_min_mm": round(float(stats.get("setup_trace_min", 0.0)), 3),
        "kicad_trace_clearance_mm": round(float(stats.get("setup_trace_clearance", 0.0)), 3),
    }


def count_by(rows: list[dict], key: str, allowed: tuple[str, ...]) -> dict[str, int]:
    counts = {name: 0 for name in allowed}
    for row in rows:
        value = row.get(key)
        if value in counts:
            counts[value] += 1
    return counts


def reference_change_summary(rows: list[dict]) -> str:
    reference_rows = [row for row in rows if row.get("Source") == "Reference" and row.get("Status") != "PASS"]
    if not reference_rows:
        return "No reference changes detected."

    board_changes = 0
    drill_changes = 0
    component_changes = 0
    for row in reference_rows:
        rule = (row.get("Rule") or "").lower()
        if "board width" in rule or "board height" in rule:
            board_changes += 1
        elif "component" in rule or "rotation delta" in rule or "position delta" in rule:
            component_changes += 1
        else:
            drill_changes += 1

    return (
        f"{drill_changes} drill-related changes, "
        f"{component_changes} component-related changes, "
        f"{board_changes} board-size changes"
    )


def encode_image_png(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def encode_pdf_bytes(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def system_info() -> dict:
    demo_reference = load_demo_reference()
    sample_geometry = demo_reference[0] if demo_reference else None
    return {
        "ai_available": ai_available(),
        "ai_provider": get_available_provider(),
        "default_ai_model": default_model_for_available_provider(),
        "bundled_reference_available": demo_reference is not None,
        "bundled_reference_name": DEMO_REFERENCE_PATH.name if demo_reference else None,
        "custom_rules": default_rules(None),
        "triac_sample_rules": default_rules(sample_geometry),
        "default_tolerances": {
            "board_tolerance": 0.10,
            "drill_position_tolerance": 0.25,
            "drill_diameter_tolerance": 0.05,
            "component_position_tolerance": 0.25,
            "component_rotation_tolerance": 1.0,
        },
    }


def run_validation(
    *,
    candidate_name: str,
    candidate_payload: bytes,
    rules: dict,
    tolerances: dict,
    reference_name: str | None = None,
    reference_payload: bytes | None = None,
    use_bundled_reference: bool = False,
    include_ai: bool = False,
    ai_model: str | None = None,
) -> dict:
    candidate_geometry, candidate_extension = parse_geometry(candidate_name, candidate_payload)

    reference_geometry = None
    reference_label = None
    if reference_payload and reference_name:
        reference_geometry, _ = parse_geometry(reference_name, reference_payload)
        reference_label = reference_name
    elif use_bundled_reference:
        bundled = load_demo_reference()
        if bundled is not None:
            reference_geometry = bundled[0]
            reference_label = DEMO_REFERENCE_PATH.name

    rule_results, rule_summary = validate_cad_geometry(candidate_geometry, rules)

    reference_results: list[dict] = []
    reference_summary = None
    if reference_geometry is not None:
        reference_results, reference_summary = compare_geometry_to_reference(
            candidate_geometry,
            reference_geometry,
            board_tolerance=float(tolerances.get("board_tolerance", 0.10)),
            drill_position_tolerance=float(tolerances.get("drill_position_tolerance", 0.25)),
            drill_diameter_tolerance=float(tolerances.get("drill_diameter_tolerance", 0.05)),
            component_position_tolerance=float(tolerances.get("component_position_tolerance", 0.25)),
            component_rotation_tolerance=float(tolerances.get("component_rotation_tolerance", 1.0)),
        )

    combined_results = rule_results + reference_results
    combined = combined_summary(rule_summary, reference_summary)
    combined["validation_score"] = calculate_validation_score(combined_results)

    failed_rows = [row for row in combined_results if row.get("Status") != "PASS"]
    category_counts = count_by(failed_rows, "Category", ("Mechanical", "Electrical", "Manufacturing"))
    severity_counts = count_by(failed_rows, "Severity", ("Critical", "Major", "Minor"))
    ref_summary_text = reference_change_summary(combined_results)

    ai_guidance = None
    ai_error = None
    if include_ai and failed_rows:
        try:
            ai_guidance = generate_validation_guidance(
                candidate_name=candidate_name,
                summary=combined,
                failed_rows=failed_rows,
                metrics=ai_metrics(candidate_geometry),
                model=ai_model.strip() if ai_model else default_model_for_available_provider(),
            )
        except Exception as exc:  # noqa: BLE001
            ai_error = str(exc)

    report_bytes = generate_pcb_validation_report(
        candidate_name=candidate_name,
        geometry=candidate_geometry,
        summary=combined,
        results=combined_results,
        reference_summary=ref_summary_text,
        ai_guidance=ai_guidance,
    )
    preview_png = encode_image_png(build_pcb_preview(candidate_geometry))

    return {
        "candidate": {
            "name": candidate_name,
            "extension": candidate_extension,
            "metrics": metrics_summary(candidate_geometry),
            "preview_png_base64": preview_png,
        },
        "reference": {
            "name": reference_label,
            "metrics": metrics_summary(reference_geometry) if reference_geometry is not None else None,
        },
        "summary": combined,
        "severity_counts": severity_counts,
        "category_counts": category_counts,
        "reference_change_summary": ref_summary_text,
        "results": combined_results,
        "failed_rows": failed_rows,
        "ai_guidance": ai_guidance,
        "ai_error": ai_error,
        "ai_available": ai_available(),
        "report": {
            "filename": f"{Path(candidate_name).stem}_validation_report.pdf",
            "pdf_base64": encode_pdf_bytes(report_bytes),
        },
    }
