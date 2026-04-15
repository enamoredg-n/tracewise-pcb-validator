"""
pcb_rule_watcher.py - background watcher for live PCB file validation.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
from dataclasses import dataclass, field

from cad_parser import parse_dxf_bytes
from cad_rules import calculate_validation_score, compare_geometry_to_reference, validate_cad_geometry
from kicad_parser import parse_kicad_pcb_bytes
from llm_assistant import ai_available, generate_validation_guidance


SUPPORTED_EXTS = {".kicad_pcb", ".dxf"}


def _parse_geometry(path: str) -> tuple[dict, str]:
    payload = open(path, "rb").read()
    lower_name = path.lower()
    if lower_name.endswith(".kicad_pcb"):
        return parse_kicad_pcb_bytes(payload), ".kicad_pcb"
    if lower_name.endswith(".dxf"):
        return parse_dxf_bytes(payload), ".dxf"
    raise ValueError("Only .kicad_pcb and .dxf are supported.")


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


@dataclass
class PCBWatcherConfig:
    enabled: bool = False
    watch_path: str = ""
    output_dir: str = "pcb_watch_output"
    reference_path: str = ""
    rules: dict = field(default_factory=dict)
    board_tolerance: float = 0.1
    drill_position_tolerance: float = 0.25
    drill_diameter_tolerance: float = 0.05
    component_position_tolerance: float = 0.25
    component_rotation_tolerance: float = 1.0
    poll_interval: float = 2.0
    ai_enabled: bool = False
    ai_model: str = ""


class PCBRuleWatcherManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._config = PCBWatcherConfig()
        self._processed: set[str] = set()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def configure(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)

    def get_config(self) -> PCBWatcherConfig:
        with self._lock:
            return PCBWatcherConfig(**self._config.__dict__)

    def _loop(self):
        while True:
            config = self.get_config()
            try:
                if config.enabled and config.watch_path:
                    self._scan_once(config)
            except Exception as exc:  # noqa: BLE001
                self._write_error(config.output_dir, str(exc))
            time.sleep(max(config.poll_interval, 0.5))

    def _scan_once(self, config: PCBWatcherConfig):
        watch_path = os.path.abspath(config.watch_path)
        output_dir = os.path.abspath(config.output_dir or "pcb_watch_output")
        os.makedirs(output_dir, exist_ok=True)

        candidates: list[str] = []
        if os.path.isfile(watch_path):
            ext = os.path.splitext(watch_path)[1].lower()
            if ext in SUPPORTED_EXTS:
                candidates.append(watch_path)
        elif os.path.isdir(watch_path):
            for name in sorted(os.listdir(watch_path)):
                path = os.path.join(watch_path, name)
                if os.path.isfile(path) and os.path.splitext(path)[1].lower() in SUPPORTED_EXTS:
                    candidates.append(path)

        for path in candidates:
            fingerprint = self._fingerprint(path)
            with self._lock:
                already_done = fingerprint in self._processed
            if already_done:
                continue

            self._process_file(path, config, output_dir)
            with self._lock:
                self._processed.add(fingerprint)
                if len(self._processed) > 5000:
                    self._processed = set(list(self._processed)[-2500:])

    def _fingerprint(self, path: str) -> str:
        stat = os.stat(path)
        return f"{os.path.abspath(path)}|{stat.st_size}|{int(stat.st_mtime_ns)}"

    def _process_file(self, path: str, config: PCBWatcherConfig, output_dir: str):
        geometry, extension = _parse_geometry(path)
        rule_results, rule_summary = validate_cad_geometry(geometry, config.rules or {})

        reference_results: list[dict] = []
        reference_summary = None
        reference_label = ""
        if config.reference_path and os.path.isfile(config.reference_path):
            reference_geometry, _ = _parse_geometry(config.reference_path)
            reference_label = os.path.basename(config.reference_path)
            reference_results, reference_summary = compare_geometry_to_reference(
                geometry,
                reference_geometry,
                board_tolerance=config.board_tolerance,
                drill_position_tolerance=config.drill_position_tolerance,
                drill_diameter_tolerance=config.drill_diameter_tolerance,
                component_position_tolerance=config.component_position_tolerance,
                component_rotation_tolerance=config.component_rotation_tolerance,
            )

        combined_results = rule_results + reference_results
        combined_summary = _combined_summary(rule_summary, reference_summary)
        combined_summary["validation_score"] = calculate_validation_score(combined_results)
        failed_rows = [row for row in combined_results if row["Status"] != "PASS"]

        ai_guidance = ""
        if config.ai_enabled and ai_available():
            try:
                ai_guidance = generate_validation_guidance(
                    candidate_name=os.path.basename(path),
                    summary=combined_summary,
                    failed_rows=failed_rows,
                    metrics=_ai_metrics(geometry),
                    model=config.ai_model or None,
                )
            except Exception as exc:  # noqa: BLE001
                ai_guidance = f"AI guidance failed: {exc}"

        base_name = os.path.splitext(os.path.basename(path))[0]
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        result_dir = os.path.join(output_dir, f"{base_name}_{stamp}")
        os.makedirs(result_dir, exist_ok=True)

        payload = {
            "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            "source_file": os.path.abspath(path),
            "source_extension": extension,
            "reference_file": os.path.abspath(config.reference_path) if config.reference_path else "",
            "reference_label": reference_label,
            "overall_status": combined_summary["overall_status"],
            "n_pass": combined_summary["n_pass"],
            "n_fail": combined_summary["n_fail"],
            "n_warn": combined_summary["n_warn"],
            "validation_score": combined_summary["validation_score"],
            "reference_change_summary": _reference_change_summary(combined_results),
            "results": combined_results,
            "metrics": _ai_metrics(geometry),
            "ai_guidance": ai_guidance,
            "output_dir": result_dir,
        }

        with open(os.path.join(result_dir, "result.json"), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

        if ai_guidance:
            with open(os.path.join(result_dir, "ai_guidance.md"), "w", encoding="utf-8") as handle:
                handle.write(ai_guidance)

    def _write_error(self, output_dir: str, message: str):
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, "_watcher_errors.log")
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {message}\n")


def load_recent_results(output_dir: str, limit: int = 10) -> list[dict]:
    if not os.path.isdir(output_dir):
        return []

    records = []
    for name in os.listdir(output_dir):
        result_path = os.path.join(output_dir, name, "result.json")
        if os.path.isfile(result_path):
            try:
                with open(result_path, encoding="utf-8") as handle:
                    payload = json.load(handle)
                records.append(payload)
            except Exception:  # noqa: BLE001
                continue

    records.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return records[:limit]
