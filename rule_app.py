"""
rule_app.py - focused Streamlit UI for exact PCB file validation.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from cad_parser import parse_dxf_bytes
from cad_rules import calculate_validation_score, compare_geometry_to_reference, validate_cad_geometry
from kicad_parser import parse_kicad_pcb_bytes
from llm_assistant import (
    ai_available,
    default_model_for_available_provider,
    generate_validation_guidance,
    get_available_provider,
)
from pcb_report_generator import generate_pcb_validation_report


LOCAL_TRIAC_REFERENCE = Path("pcb_files/kicad/TRIAC/TRIAC.kicad_pcb")


def _resolve_local_path(path_value: str) -> str:
    path_value = (path_value or "").strip()
    if not path_value:
        return str(Path(".").resolve())
    candidate = Path(path_value)
    if candidate.is_absolute():
        return str(candidate)
    return str((Path(".") / candidate).resolve())


@st.cache_resource
def _get_pcb_watcher_manager():
    from pcb_rule_watcher import PCBRuleWatcherManager

    return PCBRuleWatcherManager()


def _parse_geometry(name: str, payload: bytes) -> tuple[dict, str]:
    lower_name = name.lower()
    if lower_name.endswith(".kicad_pcb"):
        return parse_kicad_pcb_bytes(payload), ".kicad_pcb"
    if lower_name.endswith(".dxf"):
        return parse_dxf_bytes(payload), ".dxf"
    raise ValueError("Upload a .kicad_pcb or .dxf file.")


@st.cache_data
def _load_local_reference() -> tuple[dict, str] | None:
    if not LOCAL_TRIAC_REFERENCE.is_file():
        return None
    payload = LOCAL_TRIAC_REFERENCE.read_bytes()
    geometry, extension = _parse_geometry(LOCAL_TRIAC_REFERENCE.name, payload)
    return geometry, extension


def _rule_defaults(preset_name: str, sample_geometry: dict | None) -> dict:
    if preset_name == "TRIAC sample limits" and sample_geometry is not None:
        stats = sample_geometry["stats"]
        bbox = sample_geometry["bbox"]
        return {
            "expected_drill_count": int(stats.get("n_drills", 0)),
            "expected_plated_drill_count": int(stats.get("n_plated_drills", 0)),
            "expected_mounting_hole_count": int(stats.get("n_mounting_holes", 0)),
            "min_hole_diameter": float(stats.get("min_drill_diameter", 0.0)),
            "max_hole_diameter": float(stats.get("max_drill_diameter", 0.0)),
            "min_trace_width": float(
                stats.get("setup_trace_min") or stats.get("min_track_width", 0.0)
            ),
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


def _combined_summary(*summaries: dict | None) -> dict:
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


def _show_summary(summary: dict):
    if summary["overall_status"] == "FAIL":
        st.error(
            f"Validation failed: {summary['n_fail']} fail, "
            f"{summary['n_warn']} warning, {summary['n_pass']} pass."
        )
    elif summary["overall_status"] == "WARN":
        st.warning(
            f"Validation finished with warnings: {summary['n_warn']} warning, "
            f"{summary['n_pass']} pass."
        )
    else:
        st.success(f"Validation passed: {summary['n_pass']} checks passed.")


def _show_geometry_metrics(geometry: dict, file_label: str):
    bbox = geometry["bbox"]
    stats = geometry.get("stats", {})

    st.markdown(f"### Measured PCB Data: {file_label}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Board width (mm)", f"{bbox['width']:.3f}")
    c2.metric("Board height (mm)", f"{bbox['height']:.3f}")
    c3.metric("Total drills", int(stats.get("n_drills", stats.get("n_circles", 0))))
    c4.metric("Components", int(stats.get("n_components", 0)))

    c5, c6, c7 = st.columns(3)
    c5.metric("Plated drills", int(stats.get("n_plated_drills", 0)))
    c6.metric("Min drill (mm)", f"{float(stats.get('min_drill_diameter', 0.0)):.3f}")
    c7.metric("Max drill (mm)", f"{float(stats.get('max_drill_diameter', 0.0)):.3f}")
    st.caption(
        f"Mounting holes: {int(stats.get('n_mounting_holes', 0))} | "
        f"Tracks: {int(stats.get('n_tracks', 0))} | "
        f"Signal nets: {int(stats.get('n_signal_nets', 0))} | "
        f"Unrouted signal nets: {int(stats.get('n_unrouted_signal_nets', 0))} | "
        f"Min track width: {float(stats.get('min_track_width', 0.0)):.3f} mm | "
        f"KiCad trace min: {float(stats.get('setup_trace_min', 0.0)):.3f} mm | "
        f"KiCad clearance: {float(stats.get('setup_trace_clearance', 0.0)):.3f} mm"
    )


def _ai_metrics(geometry: dict) -> dict:
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


def _disable_live_refresh():
    st.session_state["pcb_watcher_auto_refresh"] = False


def _count_by(rows: list[dict], key: str, allowed: tuple[str, ...]) -> dict[str, int]:
    counts = {name: 0 for name in allowed}
    for row in rows:
        value = row.get(key)
        if value in counts:
            counts[value] += 1
    return counts


def _reference_change_summary(rows: list[dict]) -> str:
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


def _rows_frame(rows: list[dict], ordered_cols: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for column in ordered_cols:
        if column not in frame.columns:
            frame[column] = ""
    return frame[ordered_cols]


def _inject_theme():
    st.markdown(
        """
        <style>
        :root {
            --bg-1: #eef4ff;
            --bg-2: #dceaff;
            --panel: rgba(255, 255, 255, 0.78);
            --panel-strong: rgba(255, 255, 255, 0.92);
            --stroke: rgba(76, 117, 182, 0.16);
            --text-main: #10233f;
            --text-dim: #506586;
            --accent-a: #0bb9d4;
            --accent-b: #2b73ff;
            --accent-c: #ffb864;
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(43, 127, 255, 0.14), transparent 28%),
                radial-gradient(circle at top right, rgba(11, 185, 212, 0.12), transparent 26%),
                linear-gradient(180deg, var(--bg-1) 0%, #edf4ff 38%, #e0ebff 100%);
            color: var(--text-main);
        }

        .main .block-container {
            max-width: 1280px;
            padding-top: 1.4rem;
            padding-bottom: 3rem;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(7, 17, 31, 0.96), rgba(8, 20, 38, 0.98));
            border-right: 1px solid rgba(255, 255, 255, 0.06);
        }

        .site-nav {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 18px;
            padding: 18px 22px;
            margin-bottom: 1.1rem;
            border-radius: 24px;
            background: rgba(255, 255, 255, 0.76);
            border: 1px solid rgba(61, 104, 174, 0.12);
            box-shadow: 0 18px 36px rgba(87, 118, 171, 0.08);
            animation: fadeUp 0.65s ease;
        }

        .site-brand {
            font-size: 1.15rem;
            font-weight: 900;
            color: #10233f;
            margin-bottom: 3px;
        }

        .site-meta {
            color: #5a6f8d;
            font-size: 0.92rem;
            line-height: 1.55;
        }

        .site-nav-links {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            justify-content: flex-end;
        }

        .site-link-pill {
            padding: 9px 13px;
            border-radius: 999px;
            background: rgba(16, 35, 63, 0.05);
            border: 1px solid rgba(61, 104, 174, 0.1);
            color: #35557b;
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: 0.03em;
        }

        .hero-shell {
            position: relative;
            overflow: hidden;
            border-radius: 28px;
            padding: 40px 36px 34px 36px;
            background:
                linear-gradient(135deg, rgba(13, 22, 40, 0.97), rgba(18, 56, 88, 0.92) 55%, rgba(9, 24, 46, 0.97));
            border: 1px solid rgba(142, 188, 255, 0.24);
            box-shadow: 0 30px 70px rgba(44, 74, 124, 0.18);
            animation: fadeUp 0.65s ease;
            margin-bottom: 1.4rem;
        }

        .hero-shell::before {
            content: "";
            position: absolute;
            inset: -20% auto auto 55%;
            width: 340px;
            height: 340px;
            border-radius: 999px;
            background: radial-gradient(circle, rgba(30, 203, 225, 0.24), transparent 65%);
            filter: blur(8px);
            pointer-events: none;
        }

        .hero-kicker {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 14px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.07);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: #c7dcff;
            font-size: 0.82rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-weight: 700;
        }

        .hero-title {
            margin: 16px 0 10px 0;
            font-size: clamp(2rem, 3.6vw, 3.25rem);
            line-height: 1.02;
            font-weight: 800;
            color: #f4f8ff;
            max-width: 760px;
        }

        .hero-sub {
            color: #cad8ef;
            max-width: 760px;
            font-size: 1.05rem;
            line-height: 1.7;
        }

        .hero-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
            margin-top: 20px;
        }

        .hero-layout {
            display: grid;
            grid-template-columns: 1.18fr 0.82fr;
            gap: 18px;
            align-items: stretch;
        }

        .hero-sidecard {
            background: rgba(255, 255, 255, 0.07);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 24px;
            padding: 22px;
            min-height: 100%;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
            animation: floaty 5s ease-in-out infinite;
        }

        .hero-visual {
            position: relative;
            min-height: 320px;
            border-radius: 24px;
            overflow: hidden;
            background:
                radial-gradient(circle at 18% 18%, rgba(19, 203, 225, 0.3), transparent 26%),
                radial-gradient(circle at 82% 24%, rgba(255, 184, 100, 0.24), transparent 22%),
                linear-gradient(160deg, rgba(15, 29, 55, 0.98), rgba(17, 74, 111, 0.94));
            border: 1px solid rgba(255, 255, 255, 0.12);
            box-shadow: 0 26px 64px rgba(5, 18, 38, 0.28);
            padding: 22px;
        }

        .hero-orb {
            position: absolute;
            border-radius: 999px;
            filter: blur(4px);
            opacity: 0.7;
            animation: floaty 6.5s ease-in-out infinite;
        }

        .hero-orb.one {
            width: 120px;
            height: 120px;
            top: 22px;
            right: 32px;
            background: radial-gradient(circle, rgba(255,255,255,0.35), rgba(43,127,255,0.0) 72%);
        }

        .hero-orb.two {
            width: 160px;
            height: 160px;
            bottom: -10px;
            left: -20px;
            background: radial-gradient(circle, rgba(11,185,212,0.24), rgba(11,185,212,0.0) 70%);
            animation-duration: 7.2s;
        }

        .hero-stack {
            position: relative;
            display: flex;
            flex-direction: column;
            gap: 12px;
            z-index: 2;
            margin-top: 44px;
        }

        .hero-stack-card {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 18px;
            padding: 14px 16px;
            color: #edf5ff;
            backdrop-filter: blur(8px);
            animation: fadeUp 0.7s ease;
        }

        .hero-stack-label {
            font-size: 0.75rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #b8d1f5;
            font-weight: 800;
            margin-bottom: 6px;
        }

        .hero-stack-value {
            font-size: 1rem;
            font-weight: 800;
            color: #f8fbff;
            margin-bottom: 4px;
        }

        .hero-stack-copy {
            font-size: 0.9rem;
            color: #d2e0f6;
            line-height: 1.58;
        }

        .hero-sidecard-title {
            font-size: 1.05rem;
            color: #f6fbff;
            font-weight: 800;
            margin-bottom: 10px;
        }

        .hero-sidecard-copy {
            color: #d5e2f4;
            line-height: 1.72;
            font-size: 0.95rem;
        }

        .hero-actions {
            display: flex;
            gap: 12px;
            align-items: center;
            margin-top: 18px;
            flex-wrap: wrap;
        }

        .hero-mini-chip {
            display: inline-flex;
            align-items: center;
            padding: 8px 12px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: #d5e5ff;
            font-size: 0.82rem;
            font-weight: 700;
        }

        .hero-chip, .panel-card, .workflow-step {
            background: rgba(255, 255, 255, 0.8);
            border: 1px solid rgba(61, 104, 174, 0.12);
            border-radius: 20px;
            box-shadow: 0 18px 40px rgba(64, 98, 150, 0.08);
        }

        .hero-chip {
            padding: 15px 16px;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
        }

        .hero-chip-label {
            color: #bdd3f5;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
            margin-bottom: 6px;
        }

        .hero-chip-value {
            color: #f7fbff;
            font-size: 1rem;
            font-weight: 700;
        }

        .panel-card {
            padding: 24px 24px 22px 24px;
            margin-bottom: 1.2rem;
            animation: fadeUp 0.7s ease;
        }

        .panel-title {
            font-size: 1.12rem;
            font-weight: 700;
            color: #132947;
            margin-bottom: 10px;
        }

        .panel-sub {
            color: var(--text-dim);
            line-height: 1.72;
            font-size: 0.98rem;
        }

        .workflow-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
            margin-top: 8px;
        }

        .workflow-step {
            padding: 22px 20px;
            position: relative;
            overflow: hidden;
            min-height: 176px;
        }

        .workflow-step::after {
            content: "";
            position: absolute;
            inset: auto -20px -20px auto;
            width: 80px;
            height: 80px;
            border-radius: 999px;
            background: radial-gradient(circle, rgba(43, 127, 255, 0.24), transparent 72%);
        }

        .workflow-num {
            width: 30px;
            height: 30px;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.8rem;
            font-weight: 800;
            color: white;
            background: linear-gradient(135deg, var(--accent-a), var(--accent-b));
            margin-bottom: 10px;
        }

        .workflow-title {
            color: #16304f;
            font-weight: 700;
            margin-bottom: 6px;
        }

        .workflow-copy {
            color: var(--text-dim);
            font-size: 0.95rem;
            line-height: 1.62;
        }

        .story-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 16px;
            margin-bottom: 1.1rem;
        }

        .story-card {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(245, 249, 255, 0.88));
            border: 1px solid rgba(61, 104, 174, 0.12);
            border-radius: 24px;
            padding: 24px;
            min-height: 220px;
            box-shadow: 0 20px 38px rgba(87, 118, 171, 0.1);
            animation: fadeUp 0.7s ease;
        }

        .story-kicker {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #5e79a0;
            font-weight: 800;
            margin-bottom: 12px;
        }

        .story-title {
            font-size: 1.25rem;
            line-height: 1.25;
            font-weight: 800;
            color: #132a47;
            margin-bottom: 10px;
        }

        .story-copy {
            color: #536987;
            line-height: 1.72;
            font-size: 0.97rem;
        }

        .architecture-shell {
            background: linear-gradient(135deg, rgba(18, 31, 54, 0.98), rgba(20, 77, 118, 0.92));
            border-radius: 28px;
            padding: 30px;
            color: white;
            margin-bottom: 1.2rem;
            box-shadow: 0 24px 60px rgba(36, 67, 110, 0.2);
        }

        .architecture-title {
            font-size: 1.35rem;
            font-weight: 800;
            margin-bottom: 8px;
            color: #f5f8ff;
        }

        .architecture-sub {
            color: #c7d9f6;
            line-height: 1.7;
            margin-bottom: 20px;
        }

        .architecture-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 16px;
            margin-bottom: 18px;
        }

        .architecture-node {
            position: relative;
            padding: 22px 20px;
            border-radius: 22px;
            min-height: 190px;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.1);
            overflow: hidden;
            animation: pulseGlow 4.6s ease-in-out infinite;
        }

        .architecture-node::after {
            content: "";
            position: absolute;
            right: -20px;
            bottom: -20px;
            width: 100px;
            height: 100px;
            border-radius: 999px;
            background: radial-gradient(circle, rgba(255, 255, 255, 0.18), transparent 72%);
        }

        .architecture-tag {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 34px;
            height: 34px;
            border-radius: 999px;
            background: linear-gradient(135deg, var(--accent-a), var(--accent-b));
            color: white;
            font-weight: 800;
            margin-bottom: 12px;
        }

        .architecture-node-title {
            font-weight: 800;
            font-size: 1.02rem;
            margin-bottom: 8px;
            color: #f7fbff;
        }

        .architecture-node-copy {
            color: #d5e3fb;
            line-height: 1.66;
            font-size: 0.95rem;
        }

        .diagram-strip {
            display: grid;
            grid-template-columns: 1fr auto 1fr auto 1fr auto 1fr;
            gap: 10px;
            align-items: center;
            margin-top: 18px;
        }

        .diagram-box {
            min-height: 118px;
            border-radius: 22px;
            padding: 18px 16px;
            background: rgba(255, 255, 255, 0.09);
            border: 1px solid rgba(255, 255, 255, 0.11);
            animation: fadeUp 0.8s ease;
        }

        .diagram-box-title {
            color: #f7fbff;
            font-weight: 800;
            margin-bottom: 8px;
        }

        .diagram-box-copy {
            color: #d4e2f6;
            line-height: 1.65;
            font-size: 0.92rem;
        }

        .diagram-arrow {
            display: flex;
            align-items: center;
            justify-content: center;
            color: #93dfff;
            font-size: 2rem;
            font-weight: 900;
            animation: slidePulse 1.8s ease-in-out infinite;
        }

        .showcase-band {
            display: grid;
            grid-template-columns: 1.15fr 0.85fr;
            gap: 18px;
            margin-bottom: 1.1rem;
        }

        .feature-list {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
            margin-top: 12px;
        }

        .feature-tile {
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid rgba(61, 104, 174, 0.12);
            border-radius: 20px;
            padding: 18px;
            min-height: 138px;
        }

        .feature-title {
            color: #173250;
            font-weight: 800;
            margin-bottom: 8px;
        }

        .feature-copy {
            color: #57708f;
            line-height: 1.68;
            font-size: 0.95rem;
        }

        .cta-shell {
            background: linear-gradient(135deg, rgba(18, 34, 60, 0.96), rgba(25, 90, 145, 0.92));
            border-radius: 28px;
            padding: 30px;
            margin-top: 1rem;
            margin-bottom: 1.4rem;
            color: white;
            text-align: center;
        }

        .cta-title {
            font-size: 1.5rem;
            font-weight: 800;
            margin-bottom: 10px;
        }

        .cta-copy {
            color: #d2e3ff;
            max-width: 760px;
            margin: 0 auto 8px auto;
            line-height: 1.7;
        }

        .top-action-shell {
            display: flex;
            justify-content: flex-end;
            align-items: center;
            gap: 12px;
            margin-top: -0.2rem;
            margin-bottom: 1.1rem;
            animation: fadeUp 0.7s ease;
        }

        .top-action-note {
            color: #567192;
            font-size: 0.9rem;
            font-weight: 700;
        }

        .validate-hero {
            position: relative;
            overflow: hidden;
            border-radius: 24px;
            padding: 24px 24px 22px 24px;
            margin-bottom: 1rem;
            background: linear-gradient(135deg, rgba(13, 31, 58, 0.96), rgba(23, 94, 148, 0.92));
            color: white;
            box-shadow: 0 22px 50px rgba(68, 101, 150, 0.16);
        }

        .validate-hero::after {
            content: "";
            position: absolute;
            width: 180px;
            height: 180px;
            right: -40px;
            top: -30px;
            border-radius: 999px;
            background: radial-gradient(circle, rgba(255, 255, 255, 0.2), transparent 68%);
        }

        .validate-hero-title {
            font-size: 1.35rem;
            font-weight: 800;
            margin-bottom: 8px;
        }

        .validate-hero-copy {
            color: #d5e6ff;
            line-height: 1.72;
            max-width: 900px;
        }

        .validate-flow {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
            margin-top: 18px;
        }

        .validate-flow-item {
            border-radius: 18px;
            padding: 16px;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.08);
            animation: floaty 6s ease-in-out infinite;
        }

        .validate-flow-title {
            font-weight: 800;
            margin-bottom: 6px;
            color: #f8fbff;
        }

        .validate-flow-copy {
            color: #d9e6f9;
            font-size: 0.92rem;
            line-height: 1.62;
        }

        div[data-testid="stFileUploader"] {
            background: rgba(255, 255, 255, 0.72);
            border: 1px dashed rgba(61, 104, 174, 0.18);
            padding: 12px;
            box-shadow: 0 14px 24px rgba(87, 118, 171, 0.05);
        }

        div[data-testid="stTextInput"],
        div[data-testid="stNumberInput"],
        div[data-testid="stSelectbox"],
        div[data-testid="stTextArea"] {
            background: rgba(255, 255, 255, 0.54);
            border: 1px solid rgba(61, 104, 174, 0.1);
            border-radius: 18px;
            padding: 10px 12px 4px 12px;
            box-shadow: 0 12px 24px rgba(87, 118, 171, 0.04);
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
            background: rgba(255, 255, 255, 0.54);
            padding: 8px;
            border-radius: 18px;
            border: 1px solid rgba(61, 104, 174, 0.12);
            margin-bottom: 1rem;
        }

        .stTabs [data-baseweb="tab"] {
            height: 50px;
            border-radius: 14px;
            color: #5a7294;
            font-weight: 700;
            padding: 0 18px;
            transition: all 0.2s ease;
        }

        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, rgba(43, 127, 255, 0.92), rgba(30, 203, 225, 0.9));
            color: white !important;
            box-shadow: 0 14px 28px rgba(30, 203, 225, 0.18);
        }

        div[data-testid="stMetric"] {
            background: var(--panel);
            border: 1px solid var(--stroke);
            border-radius: 18px;
            padding: 14px 16px;
            box-shadow: 0 14px 30px rgba(92, 120, 169, 0.09);
        }

        div[data-testid="stMetric"] label {
            color: #6a83a6 !important;
        }

        div[data-testid="stMetricValue"] {
            color: #112641 !important;
        }

        .stButton > button {
            border: 0;
            border-radius: 14px;
            background: linear-gradient(135deg, var(--accent-b), var(--accent-a));
            color: white;
            font-weight: 700;
            box-shadow: 0 18px 30px rgba(28, 118, 244, 0.22);
        }

        .stButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 22px 38px rgba(28, 118, 244, 0.28);
        }

        div[data-testid="stFileUploader"],
        div[data-testid="stExpander"],
        div[data-testid="stDataFrame"],
        div[data-testid="stAlert"] {
            border-radius: 18px !important;
        }

        @keyframes fadeUp {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes floaty {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-5px); }
        }

        @keyframes pulseGlow {
            0%, 100% { box-shadow: 0 0 0 rgba(147, 223, 255, 0.0); }
            50% { box-shadow: 0 0 24px rgba(147, 223, 255, 0.08); }
        }

        @keyframes slidePulse {
            0%, 100% { transform: translateX(0px); opacity: 0.85; }
            50% { transform: translateX(6px); opacity: 1; }
        }

        @media (max-width: 1100px) {
            .hero-grid, .workflow-grid, .story-grid, .architecture-grid, .feature-list, .validate-flow {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .showcase-band {
                grid-template-columns: minmax(0, 1fr);
            }
            .hero-layout {
                grid-template-columns: minmax(0, 1fr);
            }
            .diagram-strip {
                grid-template-columns: minmax(0, 1fr);
            }
            .diagram-arrow {
                transform: rotate(90deg);
            }
        }

        @media (max-width: 700px) {
            .hero-grid, .workflow-grid, .story-grid, .architecture-grid, .feature-list, .validate-flow {
                grid-template-columns: minmax(0, 1fr);
            }
            .top-action-shell {
                justify-content: stretch;
                flex-direction: column;
                align-items: stretch;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _hide_sidebar():
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            display: none !important;
        }
        .main .block-container {
            padding-left: 2rem;
            padding-right: 2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_hero(ai_provider: str | None):
    ai_label = ai_provider.upper() if ai_provider else "OFF"
    st.markdown(
        f"""
        <div class="hero-shell">
            <div class="hero-layout">
                <div>
                    <div class="hero-kicker">PCB Design Intelligence Platform</div>
                    <div class="hero-title">AI-assisted PCB validation that looks like a product, not a classroom demo.</div>
                    <div class="hero-sub">
                        Real KiCad board in. Exact PCB rules out. AI guidance on top. One screen to present the story and one screen to run the tool.
                    </div>
                    <div class="hero-actions">
                        <div class="hero-mini-chip">Real PCB file parsing</div>
                        <div class="hero-mini-chip">Reference-aware validation</div>
                        <div class="hero-mini-chip">Live watcher + AI copilot</div>
                    </div>
                </div>
                <div class="hero-visual">
                    <div class="hero-orb one"></div>
                    <div class="hero-orb two"></div>
                    <div class="hero-stack">
                        <div class="hero-stack-card">
                            <div class="hero-stack-label">INPUT</div>
                            <div class="hero-stack-value">KiCad Board + Reference</div>
                            <div class="hero-stack-copy">The system reads the real board file instead of guessing from screenshots.</div>
                        </div>
                        <div class="hero-stack-card">
                            <div class="hero-stack-label">ENGINE</div>
                            <div class="hero-stack-value">Rules + Electrical Checks</div>
                            <div class="hero-stack-copy">Board size, drills, traces, spacing, components, routing, and drift are checked exactly.</div>
                        </div>
                        <div class="hero-stack-card">
                            <div class="hero-stack-label">AI COPILOT</div>
                            <div class="hero-stack-value">{ai_label}</div>
                            <div class="hero-stack-copy">Severity, explanation, summary, and fix-first guidance are generated from exact failures.</div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="hero-grid">
                <div class="hero-chip">
                    <div class="hero-chip-label">Core Engine</div>
                    <div class="hero-chip-value">Rule-based PCB validator</div>
                </div>
                <div class="hero-chip">
                    <div class="hero-chip-label">AI Copilot</div>
                    <div class="hero-chip-value">{ai_label}</div>
                </div>
                <div class="hero-chip">
                    <div class="hero-chip-label">Live Monitoring</div>
                    <div class="hero-chip-value">Watcher-enabled workflow</div>
                </div>
                <div class="hero-chip">
                    <div class="hero-chip-label">Reference Safety</div>
                    <div class="hero-chip-value">Drill + component comparison</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_overview(ai_provider: str | None):
    provider_label = ai_provider.capitalize() if ai_provider else "AI key not set"
    st.markdown(
        f"""
        <div class="panel-card">
            <div class="panel-title">What This Platform Does</div>
            <div class="panel-sub">
                It reads the real PCB design file, checks exact engineering rules, compares against a reference board,
                watches for live design changes, and turns exact failures into plain-English guidance through {provider_label}.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_pipeline_diagram():
    st.markdown(
        """
        <div class="architecture-shell">
            <div class="architecture-title">How The Model Works</div>
            <div class="architecture-sub">
                The system does not guess from random images. It reads the real PCB design file, extracts design facts,
                validates them against rules, compares them with a reference, then hands the exact results to the AI copilot.
            </div>
            <div class="architecture-grid">
                <div class="architecture-node">
                    <div class="architecture-tag">1</div>
                    <div class="architecture-node-title">KiCad Board In</div>
                    <div class="architecture-node-copy">The website reads the real <code>.kicad_pcb</code> board file, so the checks start from design data, not from visual guessing.</div>
                </div>
                <div class="architecture-node">
                    <div class="architecture-tag">2</div>
                    <div class="architecture-node-title">PCB Parser</div>
                    <div class="architecture-node-copy">The parser extracts board size, drills, components, traces, nets, clearances, and electrical routing facts.</div>
                </div>
                <div class="architecture-node">
                    <div class="architecture-tag">3</div>
                    <div class="architecture-node-title">Rule Engine</div>
                    <div class="architecture-node-copy">The rule layer checks hard engineering truth such as hole diameter, trace width, edge safety, spacing, and routed-net health.</div>
                </div>
                <div class="architecture-node">
                    <div class="architecture-tag">4</div>
                    <div class="architecture-node-title">Reference Compare</div>
                    <div class="architecture-node-copy">A changed board is compared to a trusted baseline to catch moved parts, changed drills, and shape drift.</div>
                </div>
                <div class="architecture-node">
                    <div class="architecture-tag">5</div>
                    <div class="architecture-node-title">Score + Severity</div>
                    <div class="architecture-node-copy">The engine groups results into Mechanical, Electrical, and Manufacturing issues, then assigns score and severity.</div>
                </div>
                <div class="architecture-node">
                    <div class="architecture-tag">6</div>
                    <div class="architecture-node-title">AI Copilot</div>
                    <div class="architecture-node-copy">The AI assistant explains the failures, suggests fixes, highlights what matters first, and prepares a cleaner final decision.</div>
                </div>
            </div>
            <div class="diagram-strip">
                <div class="diagram-box">
                    <div class="diagram-box-title">PCB File</div>
                    <div class="diagram-box-copy">Real KiCad board enters the system from the engineer workflow.</div>
                </div>
                <div class="diagram-arrow">→</div>
                <div class="diagram-box">
                    <div class="diagram-box-title">Parser</div>
                    <div class="diagram-box-copy">Extracts drills, traces, parts, nets, and board dimensions.</div>
                </div>
                <div class="diagram-arrow">→</div>
                <div class="diagram-box">
                    <div class="diagram-box-title">Rule + Compare</div>
                    <div class="diagram-box-copy">Checks exact rules and compares against the trusted reference board.</div>
                </div>
                <div class="diagram-arrow">→</div>
                <div class="diagram-box">
                    <div class="diagram-box-title">AI Output</div>
                    <div class="diagram-box-copy">Creates score, severity, categories, explanation, and next action.</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_landing_page(ai_provider: str | None):
    provider_label = ai_provider.capitalize() if ai_provider else "AI key not set"
    _hide_sidebar()
    nav_left, nav_right = st.columns([0.76, 0.24], gap="large")
    with nav_left:
        st.markdown(
            """
            <div class="site-nav">
                <div>
                    <div class="site-brand">PCB Design Intelligence</div>
                    <div class="site-meta">Early-stage validation, reference drift detection, live watcher flow, and AI-assisted explanations.</div>
                </div>
                <div class="site-nav-links">
                    <div class="site-link-pill">Home</div>
                    <div class="site-link-pill">Architecture</div>
                    <div class="site-link-pill">Validation</div>
                    <div class="site-link-pill">AI Copilot</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with nav_right:
        if st.button("Enter Validation Center", use_container_width=True, type="primary"):
            st.session_state["app_page"] = "validate"
            st.rerun()
    _render_hero(ai_provider)
    _render_overview(ai_provider)

    st.markdown(
        """
        <div class="story-grid">
            <div class="story-card">
                <div class="story-kicker">Problem</div>
                <div class="story-title">Manual board review is slow.</div>
                <div class="story-copy">
                    Engineers inspect board size, drill rules, trace health, and layout drift by hand. That burns time and still misses issues.
                </div>
            </div>
            <div class="story-card">
                <div class="story-kicker">Engine</div>
                <div class="story-title">The platform checks the real board file.</div>
                <div class="story-copy">
                    It validates the actual KiCad design, not just screenshots. The result comes from design facts like drills, traces, nets, and components.
                </div>
            </div>
            <div class="story-card">
                <div class="story-kicker">Outcome</div>
                <div class="story-title">Exact failures, then AI guidance.</div>
                <div class="story-copy">
                    The rule engine finds what broke. The AI copilot explains it, prioritizes it, and suggests what to fix first.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _render_pipeline_diagram()

    st.markdown(
        f"""
        <div class="showcase-band">
            <div class="panel-card">
                <div class="panel-title">Why This Feels Like A Real Product</div>
                <div class="panel-sub">
                    Exact engineering truth first. AI assistance second. That is why the output feels trustworthy instead of gimmicky.
                </div>
                <div class="feature-list">
                    <div class="feature-tile">
                        <div class="feature-title">Exact Rule Truth</div>
                        <div class="feature-copy">Checks board size, hole diameter, drill spacing, components, traces, clearance, and routed-net health directly from the PCB design file.</div>
                    </div>
                    <div class="feature-tile">
                        <div class="feature-title">Reference Drift Detection</div>
                        <div class="feature-copy">Highlights changed drills, moved components, and board differences against a known-good baseline.</div>
                    </div>
                    <div class="feature-tile">
                        <div class="feature-title">Live Monitor</div>
                        <div class="feature-copy">The watcher can keep checking the board folder and automatically run validation whenever a file changes.</div>
                    </div>
                    <div class="feature-tile">
                        <div class="feature-title">AI Guidance</div>
                        <div class="feature-copy">Uses {provider_label} to explain failures, prioritize what matters first, and suggest likely fixes.</div>
                    </div>
                </div>
            </div>
            <div class="panel-card">
                <div class="panel-title">What You Can Show In The Demo</div>
                <div class="panel-sub">
                    One scroll tells the story. One click opens the working tool.
                </div>
                <div class="feature-list" style="grid-template-columns:minmax(0,1fr);">
                    <div class="feature-tile">
                        <div class="feature-title">1. Show The Problem</div>
                        <div class="feature-copy">Manual review is slow, inconsistent, and late.</div>
                    </div>
                    <div class="feature-tile">
                        <div class="feature-title">2. Show The Architecture</div>
                        <div class="feature-copy">Parser, rules, reference compare, watcher, score, and AI copilot.</div>
                    </div>
                    <div class="feature-tile">
                        <div class="feature-title">3. Validate A Real Board</div>
                        <div class="feature-copy">Use the bundled TRIAC board or a changed copy to show exact issues.</div>
                    </div>
                    <div class="feature-tile">
                        <div class="feature-title">4. Show AI Fix Guidance</div>
                        <div class="feature-copy">Ask the copilot to explain the failure and what to fix first.</div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="panel-card">
            <div class="panel-title">How The Validation Center Works</div>
            <div class="panel-sub">
                Enter the working tool, choose the rules, run the board, then use the watcher and copilot on the same screen.
            </div>
            <div class="workflow-grid" style="margin-top:16px;">
                <div class="workflow-step">
                    <div class="workflow-num">1</div>
                    <div class="workflow-title">Load Design</div>
                    <div class="workflow-copy">Upload a KiCad board or point the watcher at a live file.</div>
                </div>
                <div class="workflow-step">
                    <div class="workflow-num">2</div>
                    <div class="workflow-title">Run Exact Checks</div>
                    <div class="workflow-copy">Measure drills, traces, spacing, board size, routing, and drift.</div>
                </div>
                <div class="workflow-step">
                    <div class="workflow-num">3</div>
                    <div class="workflow-title">Score + Categorize</div>
                    <div class="workflow-copy">Group issues into severity and category with a validation score.</div>
                </div>
                <div class="workflow-step">
                    <div class="workflow-num">4</div>
                    <div class="workflow-title">Explain With AI</div>
                    <div class="workflow-copy">Turn exact failures into a plain-language action plan.</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="cta-shell">
            <div class="cta-title">Presentation Website + Validation Center</div>
            <div class="cta-copy">
                Scroll here to tell the story. Enter the validation center to run the real PCB checks, show watcher results,
                and ask the AI copilot for fix guidance.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main():
    st.set_page_config(
        page_title="PCB Design Intelligence Platform",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_theme()

    if "app_page" not in st.session_state:
        st.session_state["app_page"] = "home"

    local_reference_bundle = _load_local_reference()
    local_reference_geometry = local_reference_bundle[0] if local_reference_bundle else None
    board_tolerance = 0.10
    drill_position_tolerance = 0.25
    drill_diameter_tolerance = 0.05
    component_position_tolerance = 0.25
    component_rotation_tolerance = 1.0
    ai_provider = get_available_provider()

    if st.session_state.get("app_page") == "home":
        _render_landing_page(ai_provider)
        return

    with st.sidebar:
        if st.button("Back To Home", use_container_width=True):
            st.session_state["app_page"] = "home"
            st.rerun()
        st.divider()
        st.header("Validation Setup")
        preset_options = ["Custom"]
        if local_reference_geometry is not None:
            preset_options.append("TRIAC sample limits")

        preset_name = st.selectbox("Rule preset", preset_options)
        use_local_reference = st.toggle(
            "Compare against bundled TRIAC reference",
            value=local_reference_geometry is not None,
            disabled=local_reference_geometry is None,
            help="Best for catching changed drill size, moved holes, and board-size drift.",
        )
        st.divider()
        st.subheader("AI Design Copilot")
        ai_enabled = st.toggle(
            "Enable AI explanation",
            value=ai_available(),
            disabled=not ai_available(),
            help="Requires GEMINI_API_KEY or OPENAI_API_KEY in your environment.",
        )
        ai_model = st.text_input(
            "AI model",
            value=default_model_for_available_provider(),
            disabled=not ai_available(),
            help="Used only for explanation, prioritization, and suggested fixes.",
        )

        if not ai_available():
            st.caption("Set GEMINI_API_KEY or OPENAI_API_KEY to turn on AI explanation and fix suggestions.")
        else:
            st.caption(f"Active AI provider: {get_available_provider()}")

    _render_hero(ai_provider)
    overview_tab, validate_tab, watcher_tab, copilot_tab = st.tabs(
        ["Overview", "Validate Board", "Live Monitor", "AI Copilot"]
    )

    with overview_tab:
        _render_overview(ai_provider)
        if local_reference_geometry is not None:
            st.markdown(
                """
                <div class="panel-card">
                    <div class="panel-title">Reference-Driven Validation</div>
                    <div class="panel-sub">
                        This workspace includes a bundled TRIAC reference board so you can instantly demonstrate
                        drift detection for drills, components, board size, and reference-based validation scoring.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    defaults = _rule_defaults(preset_name, local_reference_geometry)

    with validate_tab:
        st.markdown(
            """
            <div class="validate-hero">
                <div class="validate-hero-title">Validation Center</div>
                <div class="validate-hero-copy">
                    This is the working screen of the product. Upload a real PCB file, apply rule checks, compare with a reference board,
                    and then use the AI copilot to turn exact failures into a cleaner action plan.
                </div>
                <div class="validate-flow">
                    <div class="validate-flow-item">
                        <div class="validate-flow-title">Upload</div>
                        <div class="validate-flow-copy">Choose the board you want to validate.</div>
                    </div>
                    <div class="validate-flow-item">
                        <div class="validate-flow-title">Measure</div>
                        <div class="validate-flow-copy">Read drills, traces, parts, nets, and board dimensions.</div>
                    </div>
                    <div class="validate-flow-item">
                        <div class="validate-flow-title">Decide</div>
                        <div class="validate-flow-copy">Run exact rules and reference comparison.</div>
                    </div>
                    <div class="validate-flow-item">
                        <div class="validate-flow-title">Explain</div>
                        <div class="validate-flow-copy">Use AI to explain, prioritize, and suggest fixes.</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        left, right = st.columns([1.05, 1.35], gap="large")

        with left:
            st.markdown("### Upload PCB File")
            st.info("Recommended input: .kicad_pcb. DXF still works, but KiCad files carry richer drill detail.")

            candidate_file = st.file_uploader(
                "PCB file to validate",
                type=["kicad_pcb", "dxf"],
                help="Upload the board you want to validate.",
            )

            reference_file = st.file_uploader(
                "Optional reference PCB file",
                type=["kicad_pcb", "dxf"],
                help="If you upload a reference, the app will compare drill size, drill position, and board size.",
            )

            st.markdown("### Validation Rules")
            st.caption("Main checks only. Advanced tuning is tucked below so the core workflow stays simple.")
            r1, r2 = st.columns(2)
            with r1:
                expected_drill_count = st.number_input(
                    "Expected total drills",
                    min_value=0,
                    value=int(defaults["expected_drill_count"]),
                    step=1,
                    help="Main PCB count check. Set to 0 to ignore.",
                )
                max_part_width = st.number_input(
                    "Maximum board width (mm)",
                    min_value=0.0,
                    value=float(defaults["max_part_width"]),
                    step=0.1,
                    help="Main board-size check. Set to 0 to ignore.",
                )
                min_hole_diameter = st.number_input(
                    "Minimum drill diameter (mm)",
                    min_value=0.0,
                    value=float(defaults["min_hole_diameter"]),
                    step=0.1,
                    help="Main drill-size check. Set to 0 to ignore.",
                )
                min_trace_width = st.number_input(
                    "Minimum trace width (mm)",
                    min_value=0.0,
                    value=float(defaults["min_trace_width"]),
                    step=0.1,
                    help="Main copper-safety check. Set to 0 to ignore.",
                )
            with r2:
                expected_mounting_hole_count = st.number_input(
                    "Expected mounting holes",
                    min_value=0,
                    value=int(defaults["expected_mounting_hole_count"]),
                    step=1,
                    help="Useful for mechanical fit. Set to 0 to ignore.",
                )
                max_part_height = st.number_input(
                    "Maximum board height (mm)",
                    min_value=0.0,
                    value=float(defaults["max_part_height"]),
                    step=0.1,
                    help="Main board-size check. Set to 0 to ignore.",
                )
                max_hole_diameter = st.number_input(
                    "Maximum drill diameter (mm)",
                    min_value=0.0,
                    value=float(defaults["max_hole_diameter"]),
                    step=0.1,
                    help="Main drill-size check. Set to 0 to ignore.",
                )
                min_track_edge_clearance = st.number_input(
                    "Minimum track-to-edge clearance (mm)",
                    min_value=0.0,
                    value=float(defaults["min_track_edge_clearance"]),
                    step=0.1,
                    help="Main edge-safety check. Set to 0 to ignore.",
                )

            with st.expander("Advanced Validation Settings", expanded=False):
                a1, a2 = st.columns(2)
                with a1:
                    expected_plated_drill_count = st.number_input(
                        "Expected plated drills",
                        min_value=0,
                        value=int(defaults["expected_plated_drill_count"]),
                        step=1,
                        help="Leave 0 unless plated-drill count matters for this board.",
                    )
                    min_drill_spacing = st.number_input(
                        "Minimum drill spacing (mm)",
                        min_value=0.0,
                        value=float(defaults["min_drill_spacing"]),
                        step=0.1,
                        help="Checks edge-to-edge spacing between all drills.",
                    )
                    min_edge_clearance = st.number_input(
                        "Minimum drill-to-edge clearance (mm)",
                        min_value=0.0,
                        value=float(defaults["min_edge_clearance"]),
                        step=0.1,
                        help="Useful when drill edge distance is critical.",
                    )
                with a2:
                    max_trace_width = st.number_input(
                        "Maximum trace width (mm)",
                        min_value=0.0,
                        value=float(defaults["max_trace_width"]),
                        step=0.1,
                        help="Usually leave 0 unless you need an upper copper-width limit.",
                    )
                    min_component_spacing = st.number_input(
                        "Minimum component spacing (mm)",
                        min_value=0.0,
                        value=float(defaults["min_component_spacing"]),
                        step=0.1,
                        help="Checks spacing between component reference points.",
                    )
                    enable_deep_erc = st.toggle(
                        "Enable deep ERC continuity",
                        value=bool(defaults.get("enable_deep_erc", False)),
                        help="Stricter electrical check: tries to verify that every routed signal net stays connected as one copper group. Keep off unless you want deeper electrical analysis.",
                    )

            with st.expander("Reference Comparison Tolerances", expanded=False):
                t1, t2 = st.columns(2)
                with t1:
                    board_tolerance = st.number_input(
                        "Board size tolerance (mm)",
                        min_value=0.0,
                        value=board_tolerance,
                        step=0.01,
                    )
                    drill_position_tolerance = st.number_input(
                        "Drill position tolerance (mm)",
                        min_value=0.0,
                        value=drill_position_tolerance,
                        step=0.01,
                    )
                    drill_diameter_tolerance = st.number_input(
                        "Drill diameter tolerance (mm)",
                        min_value=0.0,
                        value=drill_diameter_tolerance,
                        step=0.01,
                    )
                with t2:
                    component_position_tolerance = st.number_input(
                        "Component position tolerance (mm)",
                        min_value=0.0,
                        value=component_position_tolerance,
                        step=0.01,
                    )
                    component_rotation_tolerance = st.number_input(
                        "Component rotation tolerance (deg)",
                        min_value=0.0,
                        value=component_rotation_tolerance,
                        step=0.1,
                    )

            run_validation = st.button("Validate PCB File", type="primary", use_container_width=True)

        with right:
            st.markdown(
                """
                <div class="panel-card">
                    <div class="panel-title">Validation Pipeline</div>
                    <div class="panel-sub">
                        The right side acts like your live engineering storyboard: what enters the system, what gets measured,
                        what gets compared, and what the final decision means.
                    </div>
                    <div class="diagram-strip" style="margin-top:14px;">
                        <div class="diagram-box" style="min-height:110px;">
                            <div class="diagram-box-title">Input</div>
                            <div class="diagram-box-copy">Board file enters from upload or watcher.</div>
                        </div>
                        <div class="diagram-arrow">→</div>
                        <div class="diagram-box" style="min-height:110px;">
                            <div class="diagram-box-title">Checks</div>
                            <div class="diagram-box-copy">Rules measure geometry, routing, and reference drift.</div>
                        </div>
                        <div class="diagram-arrow">→</div>
                        <div class="diagram-box" style="min-height:110px;">
                            <div class="diagram-box-title">Result</div>
                            <div class="diagram-box-copy">Score, severity, category, and fix guidance appear.</div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if local_reference_geometry is not None:
                st.markdown(
                    f"""
                    <div class="panel-card">
                        <div class="panel-title">Bundled TRIAC Reference</div>
                        <div class="panel-sub">
                            Ready-to-use reference board at <code>{LOCAL_TRIAC_REFERENCE}</code> for drill drift,
                            component movement, board-size regression, and clean demo setup.
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    rules = {
        "expected_drill_count": expected_drill_count,
        "expected_plated_drill_count": expected_plated_drill_count,
        "expected_mounting_hole_count": expected_mounting_hole_count,
        "min_hole_diameter": min_hole_diameter,
        "max_hole_diameter": max_hole_diameter,
        "min_trace_width": min_trace_width,
        "max_trace_width": max_trace_width,
        "min_edge_clearance": min_edge_clearance,
        "min_drill_spacing": min_drill_spacing,
        "min_component_spacing": min_component_spacing,
        "min_track_edge_clearance": min_track_edge_clearance,
        "max_part_width": max_part_width,
        "max_part_height": max_part_height,
        "enable_deep_erc": enable_deep_erc,
    }

    with watcher_tab:
        st.markdown(
            """
            <div class="panel-card">
                <div class="panel-title">Live KiCad Watcher</div>
                <div class="panel-sub">
                    Point this at a real <code>.kicad_pcb</code> file or folder. When the file changes,
                    the platform reruns validation automatically and updates the latest monitored result.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        watcher = _get_pcb_watcher_manager()
        watcher_config = watcher.get_config()
        default_watch_path = str(LOCAL_TRIAC_REFERENCE.resolve()) if LOCAL_TRIAC_REFERENCE.is_file() else ""
        default_watch_output = _resolve_local_path("pcb_watch_output")
        default_watch_reference = str(LOCAL_TRIAC_REFERENCE.resolve()) if LOCAL_TRIAC_REFERENCE.is_file() else ""

        if "pcb_watch_path" not in st.session_state:
            st.session_state["pcb_watch_path"] = watcher_config.watch_path or default_watch_path
        if "pcb_watch_reference_path" not in st.session_state:
            st.session_state["pcb_watch_reference_path"] = (
                watcher_config.reference_path or default_watch_reference
            )
        if "pcb_watch_output_dir" not in st.session_state:
            st.session_state["pcb_watch_output_dir"] = watcher_config.output_dir or default_watch_output
        if "pcb_watcher_enabled" not in st.session_state:
            st.session_state["pcb_watcher_enabled"] = bool(watcher_config.enabled)
        if "pcb_watcher_auto_refresh" not in st.session_state:
            st.session_state["pcb_watcher_auto_refresh"] = False
        if "pcb_watcher_auto_ai" not in st.session_state:
            st.session_state["pcb_watcher_auto_ai"] = bool(watcher_config.ai_enabled and ai_available())
        if "pcb_watcher_poll_interval" not in st.session_state:
            st.session_state["pcb_watcher_poll_interval"] = int(watcher_config.poll_interval or 2)

        watch_path = st.text_input(
            "Watched PCB file or folder",
            key="pcb_watch_path",
            help="Use the actual KiCad board file path if you want save-and-check behavior.",
        )
        watch_reference_path = st.text_input(
            "Watcher reference PCB file (optional)",
            key="pcb_watch_reference_path",
            help="Use an original board here if the watched file is a changed working copy.",
        )
        watch_output_dir = st.text_input(
            "Watcher output folder",
            key="pcb_watch_output_dir",
            help="Automatic validation results will be written here.",
        )

        w1, w2, w3, w4 = st.columns(4)
        with w1:
            watcher_enabled = st.toggle(
                "Watcher enabled",
                key="pcb_watcher_enabled",
            )
        with w2:
            watcher_auto_refresh = st.toggle(
                "Live refresh",
                key="pcb_watcher_auto_refresh",
            )
        with w3:
            watcher_auto_ai = st.toggle(
                "Auto AI guidance",
                key="pcb_watcher_auto_ai",
                disabled=not ai_available(),
            )
        with w4:
            watcher_poll_interval = st.slider(
                "Poll interval (sec)",
                min_value=1,
                max_value=15,
                key="pcb_watcher_poll_interval",
                step=1,
            )

        st.button(
            "Stop Live Refresh",
            use_container_width=True,
            on_click=_disable_live_refresh,
        )

        watcher_auto_refresh = st.session_state.get("pcb_watcher_auto_refresh", False)

        watcher.configure(
            enabled=watcher_enabled,
            watch_path=_resolve_local_path(watch_path),
            output_dir=_resolve_local_path(watch_output_dir),
            reference_path=_resolve_local_path(watch_reference_path) if watch_reference_path.strip() else "",
            rules=rules,
            board_tolerance=board_tolerance,
            drill_position_tolerance=drill_position_tolerance,
            drill_diameter_tolerance=drill_diameter_tolerance,
            component_position_tolerance=component_position_tolerance,
            component_rotation_tolerance=component_rotation_tolerance,
            poll_interval=float(watcher_poll_interval),
            ai_enabled=bool(watcher_auto_ai and ai_available()),
            ai_model=ai_model.strip() or default_model_for_available_provider(),
        )

        if watcher_enabled:
            st.success(
                f"Watching `{_resolve_local_path(watch_path)}` and writing automatic results to "
                f"`{_resolve_local_path(watch_output_dir)}`."
            )
        else:
            st.info("Watcher is idle. Turn it on to start automatic save-and-check validation.")

        from pcb_rule_watcher import load_recent_results as load_recent_pcb_results

        recent_watch_results = load_recent_pcb_results(_resolve_local_path(watch_output_dir), limit=8)
        if recent_watch_results:
            table_rows = []
            for item in recent_watch_results:
                table_rows.append(
                    {
                        "Time": item.get("timestamp", ""),
                        "File": os.path.basename(item.get("source_file", "")),
                        "Status": item.get("overall_status", ""),
                        "Score": int(item.get("validation_score", 100)),
                        "Fails": item.get("n_fail", 0),
                        "Warnings": item.get("n_warn", 0),
                    }
                )

            st.dataframe(pd.DataFrame(table_rows), use_container_width=True)

            latest_watch = recent_watch_results[0]
            st.markdown("#### Latest Automatic Result")
            st.write(
                f"File: `{os.path.basename(latest_watch.get('source_file', ''))}` | "
                f"Status: **{latest_watch.get('overall_status', '')}** | "
                f"Score: **{int(latest_watch.get('validation_score', 100))}/100** | "
                f"Fails: **{latest_watch.get('n_fail', 0)}** | "
                f"Warnings: **{latest_watch.get('n_warn', 0)}**"
            )
            st.caption(f"Reference change summary: {latest_watch.get('reference_change_summary', 'No reference changes detected.')}")

            latest_failed = [row for row in latest_watch.get("results", []) if row.get("Status") != "PASS"]
            for row in latest_failed[:6]:
                if row["Status"] == "FAIL":
                    st.error(f"{row['Source']} | {row['Rule']} | {row['Message']}")
                else:
                    st.warning(f"{row['Source']} | {row['Rule']} | {row['Message']}")

            if latest_watch.get("ai_guidance"):
                with st.expander("Latest AI Guidance", expanded=False):
                    st.markdown(latest_watch["ai_guidance"])
        else:
            st.caption("No automatic watcher results yet. Save the watched KiCad file to trigger validation.")

    if watcher_enabled and watcher_auto_refresh:
        components.html(
            f"""
            <script>
            setTimeout(function() {{
                window.parent.location.reload();
            }}, {int(max(float(watcher_poll_interval), 1.0) * 1000)});
            </script>
            """,
            height=0,
        )

    if not run_validation:
        combined_results = st.session_state.get("rule_combined_results")
        combined_summary = st.session_state.get("rule_combined_summary")
        candidate_geometry = st.session_state.get("rule_candidate_geometry")
        candidate_extension = st.session_state.get("rule_candidate_extension")
        candidate_name = st.session_state.get("rule_candidate_name")
        reference_geometry = st.session_state.get("rule_reference_geometry")
        reference_label = st.session_state.get("rule_reference_label")
    else:
        if candidate_file is None:
            st.error("Upload a PCB file first.")
            return

        with st.spinner("Parsing candidate PCB file..."):
            try:
                candidate_geometry, candidate_extension = _parse_geometry(
                    candidate_file.name,
                    candidate_file.getvalue(),
                )
            except Exception as exc:
                st.error(f"Could not parse the candidate PCB file: {exc}")
                return

        candidate_name = candidate_file.name
        reference_geometry = None
        reference_label = None
        if reference_file is not None:
            with st.spinner("Parsing reference PCB file..."):
                try:
                    reference_geometry, _ = _parse_geometry(
                        reference_file.name,
                        reference_file.getvalue(),
                    )
                    reference_label = reference_file.name
                except Exception as exc:
                    st.error(f"Could not parse the reference PCB file: {exc}")
                    return
        elif use_local_reference and local_reference_geometry is not None:
            reference_geometry = local_reference_geometry
            reference_label = LOCAL_TRIAC_REFERENCE.name

        with st.spinner("Running exact PCB rule checks..."):
            rule_results, rule_summary = validate_cad_geometry(candidate_geometry, rules)

        reference_results: list[dict] = []
        reference_summary = None
        if reference_geometry is not None:
            with st.spinner("Comparing against the reference board..."):
                reference_results, reference_summary = compare_geometry_to_reference(
                    candidate_geometry,
                    reference_geometry,
                    board_tolerance=board_tolerance,
                    drill_position_tolerance=drill_position_tolerance,
                    drill_diameter_tolerance=drill_diameter_tolerance,
                    component_position_tolerance=component_position_tolerance,
                    component_rotation_tolerance=component_rotation_tolerance,
                )

        combined_results = rule_results + reference_results
        combined_summary = _combined_summary(rule_summary, reference_summary)
        combined_summary["validation_score"] = calculate_validation_score(combined_results)

        st.session_state["rule_combined_results"] = combined_results
        st.session_state["rule_combined_summary"] = combined_summary
        st.session_state["rule_candidate_geometry"] = candidate_geometry
        st.session_state["rule_candidate_extension"] = candidate_extension
        st.session_state["rule_candidate_name"] = candidate_name
        st.session_state["rule_reference_geometry"] = reference_geometry
        st.session_state["rule_reference_label"] = reference_label
        st.session_state.pop("ai_guidance", None)

    if combined_results and combined_summary and candidate_geometry is not None:
        with validate_tab:
            st.divider()
            _show_summary(combined_summary)

            validation_score = int(combined_summary.get("validation_score", calculate_validation_score(combined_results)))
            issue_rows = [row for row in combined_results if row["Status"] != "PASS"]
            category_counts = _count_by(issue_rows, "Category", ("Mechanical", "Electrical", "Manufacturing"))
            severity_counts = _count_by(issue_rows, "Severity", ("Critical", "Major", "Minor"))

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Validation score", f"{validation_score}/100")
            m2.metric("Critical issues", severity_counts["Critical"])
            m3.metric("Major issues", severity_counts["Major"])
            m4.metric("Minor issues", severity_counts["Minor"])

            c1, c2, c3 = st.columns(3)
            c1.metric("Mechanical issues", category_counts["Mechanical"])
            c2.metric("Electrical issues", category_counts["Electrical"])
            c3.metric("Manufacturing issues", category_counts["Manufacturing"])

            st.caption(f"Reference change summary: {_reference_change_summary(combined_results)}")

            _show_geometry_metrics(candidate_geometry, f"{candidate_name} ({candidate_extension})")
            if reference_geometry is not None and reference_label is not None:
                with st.expander(f"Reference measurements: {reference_label}", expanded=False):
                    _show_geometry_metrics(reference_geometry, reference_label)

            report_pdf = generate_pcb_validation_report(
                candidate_name=candidate_name,
                geometry=candidate_geometry,
                summary=combined_summary,
                results=combined_results,
                reference_summary=_reference_change_summary(combined_results),
                ai_guidance=st.session_state.get("ai_guidance"),
            )
            st.download_button(
                "Download Validation Report",
                data=report_pdf,
                file_name=f"{Path(candidate_name).stem}_validation_report.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

            failed_rows = issue_rows

            st.markdown("### Validation Results")
            if failed_rows:
                ordered_cols = [
                    "Severity",
                    "Category",
                    "Source",
                    "Rule",
                    "Required",
                    "Found",
                    "Status",
                    "Message",
                ]
                st.dataframe(_rows_frame(failed_rows, ordered_cols), use_container_width=True)
            else:
                ordered_cols = [
                    "Category",
                    "Source",
                    "Rule",
                    "Required",
                    "Found",
                    "Status",
                    "Message",
                ]
                st.dataframe(_rows_frame(combined_results, ordered_cols), use_container_width=True)

            if failed_rows:
                st.markdown("### Exact Issues Found")
                for row in failed_rows:
                    if row["Status"] == "FAIL":
                        st.error(f"{row['Source']} | {row['Rule']} | {row['Message']}")
                    else:
                        st.warning(f"{row['Source']} | {row['Rule']} | {row['Message']}")
            else:
                st.success("No exact PCB rule issues were found for this file.")

            with st.expander("Show Full Validation Table", expanded=False):
                ordered_cols = [
                    "Severity",
                    "Category",
                    "Source",
                    "Rule",
                    "Required",
                    "Found",
                    "Status",
                    "Message",
                ]
                st.dataframe(_rows_frame(combined_results, ordered_cols), use_container_width=True)

        with copilot_tab:
            st.markdown(
                """
                <div class="panel-card">
                    <div class="panel-title">AI Design Copilot</div>
                    <div class="panel-sub">
                        The AI layer does not replace the rule engine. It reads exact failures and turns them into
                        priorities, explanations, and suggested fixes for engineers.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if ai_enabled and ai_available():
                if st.button("Generate AI Guidance", use_container_width=True):
                    with st.spinner("Generating AI explanation and fix plan..."):
                        try:
                            ai_text = generate_validation_guidance(
                                candidate_name=candidate_name,
                                summary=combined_summary,
                                failed_rows=failed_rows,
                                metrics=_ai_metrics(candidate_geometry),
                                model=ai_model.strip() or default_model_for_available_provider(),
                            )
                        except Exception as exc:
                            st.error(str(exc))
                        else:
                            st.session_state["ai_guidance"] = ai_text

                if st.session_state.get("ai_guidance"):
                    st.markdown(st.session_state["ai_guidance"])
                else:
                    st.info("Run validation first, then generate AI guidance for a cleaner engineering summary.")
            else:
                st.info(
                    "AI explanation is off right now. The rule engine already gives exact failures; "
                    "the AI layer adds prioritization, plain-English explanation, and suggested fixes."
                )
    else:
        with validate_tab:
            st.info("Upload a PCB file and run validation to populate the dashboard.")
        with copilot_tab:
            st.info("Run a validation first to unlock AI explanation and fix guidance.")


if __name__ == "__main__":
    main()
