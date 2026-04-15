"""
pcb_report_generator.py - compact 2-page PDF report for PCB validation.
"""

from __future__ import annotations

import io
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PAGE_WIDTH_MM = 210
CONTENT_WIDTH_MM = 170


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            textColor=colors.HexColor("#10233F"),
            alignment=TA_CENTER,
            spaceAfter=10,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            textColor=colors.HexColor("#5A6F8D"),
            alignment=TA_CENTER,
            spaceAfter=10,
        ),
        "heading": ParagraphStyle(
            "heading",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=colors.HexColor("#173250"),
            spaceBefore=8,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#334B68"),
            spaceAfter=5,
        ),
        "tiny": ParagraphStyle(
            "tiny",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#5A6F8D"),
            spaceAfter=4,
        ),
        "table": ParagraphStyle(
            "table",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.3,
            leading=11,
            textColor=colors.HexColor("#243A57"),
        ),
    }


def _to_rl_image(image: Image.Image, width_mm: float) -> RLImage:
    ratio = image.height / max(image.width, 1)
    height_mm = width_mm * ratio
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return RLImage(buf, width=width_mm * mm, height=height_mm * mm)


def _safe_bbox(geometry: dict) -> dict:
    bbox = geometry.get("bbox", {}) or {}
    min_x = float(bbox.get("min_x", 0.0))
    min_y = float(bbox.get("min_y", 0.0))
    max_x = float(bbox.get("max_x", min_x + 1.0))
    max_y = float(bbox.get("max_y", min_y + 1.0))
    if max_x <= min_x:
        max_x = min_x + 1.0
    if max_y <= min_y:
        max_y = min_y + 1.0
    return {
        "min_x": min_x,
        "min_y": min_y,
        "max_x": max_x,
        "max_y": max_y,
        "width": max_x - min_x,
        "height": max_y - min_y,
    }


def _preview_point(x: float, y: float, bbox: dict, width: int, height: int, pad: int):
    sx = (width - 2 * pad) / max(bbox["width"], 1e-6)
    sy = (height - 2 * pad) / max(bbox["height"], 1e-6)
    px = pad + (x - bbox["min_x"]) * sx
    py = height - pad - (y - bbox["min_y"]) * sy
    return px, py


def build_pcb_preview(geometry: dict, width: int = 1200, height: int = 700) -> Image.Image:
    bbox = _safe_bbox(geometry)
    canvas = Image.new("RGB", (width, height), "#f7fbff")
    draw = ImageDraw.Draw(canvas)
    pad = 48

    board_fill = "#ecf4ff"
    board_stroke = "#1d4d8f"
    track_color = "#0bb9d4"
    drill_color = "#1c2740"
    comp_fill = "#fff2d9"
    comp_stroke = "#c9852f"

    left_top = _preview_point(bbox["min_x"], bbox["max_y"], bbox, width, height, pad)
    right_bottom = _preview_point(bbox["max_x"], bbox["min_y"], bbox, width, height, pad)
    draw.rounded_rectangle([left_top, right_bottom], radius=28, fill=board_fill, outline=board_stroke, width=4)

    tracks = geometry.get("tracks") or []
    for track in tracks[:400]:
        p1 = _preview_point(track.start_x, track.start_y, bbox, width, height, pad)
        p2 = _preview_point(track.end_x, track.end_y, bbox, width, height, pad)
        draw.line([p1, p2], fill=track_color, width=max(2, int(track.width * 7)))

    vias = geometry.get("vias") or []
    for via in vias[:300]:
        px, py = _preview_point(via.center_x, via.center_y, bbox, width, height, pad)
        r = max(3, int(via.size * 3))
        draw.ellipse([px - r, py - r, px + r, py + r], outline="#1f6dc8", width=2, fill="#dff1ff")

    drills = geometry.get("drills") or geometry.get("circles") or []
    for drill in drills[:500]:
        px, py = _preview_point(drill.center_x, drill.center_y, bbox, width, height, pad)
        r = max(3, int(getattr(drill, "radius", 0.6) * 4))
        draw.ellipse([px - r, py - r, px + r, py + r], outline=drill_color, width=2, fill="#ffffff")

    font = ImageFont.load_default()
    components = geometry.get("components") or []
    for comp in components[:80]:
        px, py = _preview_point(comp.center_x, comp.center_y, bbox, width, height, pad)
        box = [px - 12, py - 10, px + 12, py + 10]
        draw.rounded_rectangle(box, radius=6, fill=comp_fill, outline=comp_stroke, width=2)
        ref = str(getattr(comp, "reference", ""))[:8]
        if ref:
            draw.text((px + 14, py - 7), ref, fill="#6f4e20", font=font)

    draw.text((pad, 12), "Uploaded PCB Preview", fill="#173250", font=font)
    return canvas


def _risk_solution(row: dict) -> str:
    rule = (row.get("Rule") or "").lower()
    message = (row.get("Message") or "").lower()
    text = f"{rule} {message}"

    if "board width" in text or "board height" in text:
        return "Resize the board outline so it stays inside the approved mechanical envelope."
    if "drill diameter" in text or "hole diameter" in text or "drill count" in text or "mounting hole" in text:
        return "Update the pad or drill definition so the hole setup matches the approved drill plan."
    if "drill spacing" in text:
        return "Increase spacing between the affected holes or move one footprint farther away."
    if "edge clearance" in text and "track" not in text:
        return "Move the drill or feature farther from the board edge."
    if "trace width" in text or "track width" in text:
        return "Increase the copper width or assign the net to the correct rule class."
    if "track-to-edge" in text or ("track" in text and "edge" in text):
        return "Move the copper path inward to restore the required board-edge safety margin."
    if "component spacing" in text:
        return "Reposition the affected component to keep assembly and service clearance."
    if "component" in text and ("position" in text or "rotation" in text or "moved" in text):
        return "Align the component back to the approved reference placement."
    if "routing" in text or "continuity" in text or "net" in text:
        return "Complete or repair the routing so the intended electrical connection is preserved."
    return "Review the affected feature and adjust the design to satisfy the validation rule."


def _risk_rows(results: list[dict], limit: int = 6) -> list[dict]:
    severity_order = {"Critical": 0, "Major": 1, "Minor": 2, "Pass": 9}
    issue_rows = [row for row in results if row.get("Status") != "PASS"]
    issue_rows.sort(
        key=lambda row: (
            severity_order.get(row.get("Severity"), 8),
            str(row.get("Category", "")),
            str(row.get("Rule", "")),
        )
    )
    selected = []
    for row in issue_rows[:limit]:
        selected.append(
            {
                "risk": row.get("Message") or row.get("Rule") or "Validation issue detected",
                "type": f"{row.get('Category', 'General')} / {row.get('Severity', 'Issue')}",
                "solution": _risk_solution(row),
            }
        )
    return selected


def generate_pcb_validation_report(
    *,
    candidate_name: str,
    geometry: dict,
    summary: dict,
    results: list[dict],
    reference_summary: str,
    ai_guidance: str | None = None,
) -> bytes:
    styles = _styles()
    preview = build_pcb_preview(geometry)
    risk_rows = _risk_rows(results)
    score = int(summary.get("validation_score", 0))
    status = summary.get("overall_status", "UNKNOWN")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=14 * mm,
    )
    story = []

    generated = datetime.now().strftime("%d %b %Y %H:%M")
    story.append(Paragraph("PCB Validation Report", styles["title"]))
    story.append(Paragraph(f"{candidate_name} | Generated on {generated}", styles["subtitle"]))

    summary_table = Table(
        [
            ["Overall status", status],
            ["Validation score", f"{score}/100"],
            ["Critical / Major / Minor", f"{sum(1 for r in results if r.get('Severity') == 'Critical')} / {sum(1 for r in results if r.get('Severity') == 'Major')} / {sum(1 for r in results if r.get('Severity') == 'Minor')}"],
            ["Reference summary", reference_summary],
        ],
        colWidths=[42 * mm, 128 * mm],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F8FF")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#173250")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D5E4FA")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 8))
    story.append(Paragraph("Uploaded PCB Preview", styles["heading"]))
    story.append(Paragraph("The report includes a generated visual preview of the uploaded board so reviewers can connect the validation result with the actual layout.", styles["body"]))
    story.append(_to_rl_image(preview, 165))

    story.append(PageBreak())
    story.append(Paragraph("Top Validation Risks", styles["heading"]))
    if risk_rows:
        table_data = [[
            Paragraph("<b>Major risk</b>", styles["table"]),
            Paragraph("<b>Type of risk</b>", styles["table"]),
            Paragraph("<b>Solution</b>", styles["table"]),
        ]]
        for item in risk_rows:
            table_data.append(
                [
                    Paragraph(item["risk"], styles["table"]),
                    Paragraph(item["type"], styles["table"]),
                    Paragraph(item["solution"], styles["table"]),
                ]
            )
        risk_table = Table(table_data, colWidths=[57 * mm, 42 * mm, 71 * mm], repeatRows=1)
        risk_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173250")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FBFF")),
                    ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#D4E3FA")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(risk_table)
    else:
        story.append(Paragraph("No major risks were detected in the current validation run.", styles["body"]))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Mitigation Summary", styles["heading"]))
    story.append(
        Paragraph(
            "The report keeps the core decision rule-grounded. AI guidance is used to clarify and prioritize action, while the final validation result remains tied to exact PCB checks.",
            styles["body"],
        )
    )
    if ai_guidance:
        guidance = ai_guidance.replace("\n", "<br/>")
        if len(guidance) > 900:
            guidance = guidance[:900].rsplit(" ", 1)[0] + "..."
        story.append(Paragraph("AI Guidance Snapshot", styles["heading"]))
        story.append(Paragraph(guidance, styles["tiny"]))

    doc.build(story)
    return buffer.getvalue()
