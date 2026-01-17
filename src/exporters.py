# src/exporters.py

"""Export targets for attorney-facing artifacts.

This module keeps exports as a *presentation layer* on top of the structured
Attorney Review Packet dict produced by :func:`src.packet.build_attorney_review_packet`.

Design goals:
- Single source of truth = the packet dict
- Exports are deterministic, stable, and easy to test
- Exports never mutate the packet
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def export_packet_markdown(packet: Dict[str, Any]) -> str:
    """Render an Attorney Review Packet as Markdown.

    The Markdown is intended for:
    - internal firm notes
    - quick copy/paste into an email or case management system
    - a future Markdown->PDF pipeline
    """

    meta = packet.get("meta", {})
    window_start = meta.get("window_start")
    window_end = meta.get("window_end")
    schema_version = meta.get("schema_version")

    parts: List[str] = []
    parts.append("# Attorney Review Packet")
    policy_label = ((packet.get("policy") or {}).get("name") and (packet.get("policy") or {}).get("version"))
    if schema_version:
        parts.append(f"- **Schema version:** `{schema_version}`")
    if window_start and window_end:
        parts.append(f"- **Validation window:** {window_start} → {window_end}")
    parts.append("")

    # Executive summary (lawyer-first)
    ex = packet.get("executive_summary") or {}
    if ex:
        parts.append("## Executive Summary")

        policy = (ex.get("policy") or {})
        policy_label = policy.get("label")
        if policy_label:
            parts.append(f"_Policy: {policy_label}_")

        posture = ex.get("overall_risk_posture")
        if posture:
            parts.append(f"- **Overall risk posture:** {str(posture).upper()}")

        # Top n risks
        parts.append("")
        top_n = len(ex.get("top_risks") or [])
        parts.append(f"### Top Risks (Top {top_n})")
        for idx, item in enumerate(ex.get("top_risks") or [], start=1):
            topic = item.get("topic")
            role = item.get("role")
            severity = item.get("severity")
            res_type = item.get("resolution_type")
            summary = item.get("summary")
            parts.append(f"{idx}. **{topic} ({role})** — **{severity}** — *{res_type}*")
            if summary:
                parts.append(f"   - {str(summary).strip()}")

        # Client follow-up snapshot
        follow = ex.get("client_followup") or {}
        parts.append("")
        parts.append("### Client Follow-Up")
        parts.append(f"- **Required (P0):** {follow.get('required_p0', 0)}")
        parts.append(f"- **Recommended (P1):** {follow.get('recommended_p1', 0)}")
        blocking = follow.get("blocking_topics") or []
        if blocking:
            parts.append(f"- **Blocking topics:** {', '.join(blocking)}")

        # Evidence planning snapshot
        ev = (ex.get("evidence_planning") or {}).get("items") or []
        parts.append("")
        parts.append("### Evidence Planning")
        if not ev:
            parts.append("- (none)")
        else:
            for e in ev:
                parts.append(f"- {e}")
        parts.append("")

    parts.append("# Detailed Analysis")
    parts.append("")

    # Client clarification pack (copy/paste ready)
    ccp = packet.get("client_clarification_pack")
    if ccp:
        parts.append("## Client Clarification Pack")
        email = ccp.get("email", {})
        subject = email.get("subject")
        body = email.get("body")
        if subject:
            parts.append(f"**Email subject:** {subject}")
        if body:
            parts.append("\n**Email body (copy/paste):**\n")
            parts.append("```text")
            parts.append(str(body).rstrip())
            parts.append("```")
        parts.append("")

    # Top risks
    top_risks = packet.get("top_risks", {}).get("items", [])
    parts.append("## Top Risks")
    if not top_risks:
        parts.append("No top risks generated.")
    else:
        for idx, item in enumerate(top_risks, start=1):
            topic = item.get("topic", "other")
            score = item.get("score")
            severity = item.get("severity")
            res_type = item.get("resolution_type")
            codes = (item.get("findings") or {}).get("codes") or []
            narrative = (item.get("narrative") or {}).get("rendered_text")

            parts.append(f"### {idx}. {topic}")
            parts.append(f"- **Severity:** {severity}")
            parts.append(f"- **Resolution:** {res_type}")
            if score is not None:
                parts.append(f"- **Score:** {score}")
            if codes:
                parts.append(f"- **Finding codes:** {', '.join(codes)}")
            if narrative:
                parts.append("\n" + str(narrative).strip() + "\n")
            parts.append("")

    # Issues counts summary
    issues = packet.get("issues", {})
    counts = issues.get("counts") or {}
    if counts:
        parts.append("## Issue Counts")
        for k in ("high", "medium", "low"):
            if k in counts:
                parts.append(f"- **{k.capitalize()}:** {counts[k]}")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def export_packet_pdf(packet: Dict[str, Any], output_path: str | Path) -> Path:
    """Export the packet to a simple PDF.

    This intentionally produces a *plain* PDF (no fancy layout) to keep the
    implementation stable and low-risk. Firms can still use it immediately,
    and we can iterate later on typography/branding.
    """

    # Lazy import to avoid making reportlab a hard dependency for users who
    # only want Markdown.
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out), pagesize=LETTER)
    width, height = LETTER

    x = 1.0 * inch
    y = height - 1.0 * inch
    line_h = 14

    def draw_line(text: str, bold: bool = False) -> None:
        nonlocal y
        if y < 1.0 * inch:
            c.showPage()
            y = height - 1.0 * inch
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11)
        c.drawString(x, y, text[:1200])
        y -= line_h

    meta = packet.get("meta", {})
    # Page 1: Executive Summary
    draw_line("EXECUTIVE SUMMARY — AOS TIMELINE REVIEW", bold=True)
    pol = (packet.get("executive_summary") or {}).get("policy") or {}
    label = pol.get("label")
    if label:
        draw_line(f"Policy: {label}")
    if meta.get("schema_version"):
        draw_line(f"Packet schema: {meta['schema_version']}")
    if meta.get("window_start") and meta.get("window_end"):
        draw_line(f"Analysis window: {meta['window_start']} → {meta['window_end']}")
    y -= 8

    ex = packet.get("executive_summary") or {}
    posture = ex.get("overall_risk_posture")
    if posture:
        draw_line(f"Overall risk posture: {str(posture).upper()}")
        y -= 6

    top_items = ex.get("top_risks") or []
    draw_line(f"Top Risks (Top {len(top_items)})", bold=True)
    if not top_items:
        draw_line("(none)")
    else:
        for idx, item in enumerate(top_items, start=1):
            topic = item.get("topic", "other")
            role = item.get("role", "case")
            severity = item.get("severity")
            res_type = item.get("resolution_type")
            summary = item.get("summary")
            draw_line(f"{idx}. {topic} ({role})", bold=True)
            draw_line(f"Severity: {severity} | Action: {res_type}")
            if summary:
                for line in str(summary).splitlines():
                    draw_line(line)
            y -= 4

    follow = ex.get("client_followup") or {}
    draw_line("Client Follow-Up", bold=True)
    draw_line(f"Required (P0): {follow.get('required_p0', 0)}")
    draw_line(f"Recommended (P1): {follow.get('recommended_p1', 0)}")
    blocking = follow.get("blocking_topics") or []
    if blocking:
        draw_line("Blocking topics: " + ", ".join([str(b) for b in blocking]))
    y -= 6

    draw_line("Evidence Planning", bold=True)
    ev_items = (ex.get("evidence_planning") or {}).get("items") or []
    if not ev_items:
        draw_line("(none)")
    else:
        for e in ev_items:
            draw_line(f"- {e}")

    # Page break: Detailed analysis
    c.showPage()
    y = height - 1.0 * inch

    draw_line("DETAILED ANALYSIS", bold=True)
    if meta.get("schema_version"):
        draw_line(f"Schema version: {meta['schema_version']}")
    if meta.get("window_start") and meta.get("window_end"):
        draw_line(f"Validation window: {meta['window_start']} → {meta['window_end']}")
    y -= 6

    # Client clarification pack
    ccp = packet.get("client_clarification_pack")
    if ccp:
        draw_line("Client Clarification Pack", bold=True)
        email = ccp.get("email", {})
        subject = email.get("subject")
        body = email.get("body")
        if subject:
            draw_line(f"Subject: {subject}")
        if body:
            draw_line("Body:")
            for line in str(body).splitlines():
                draw_line(line)
        y -= 8

    # Top risks
    draw_line("Top Risks", bold=True)
    items = packet.get("top_risks", {}).get("items", [])
    if not items:
        draw_line("(none)")
    else:
        for idx, item in enumerate(items, start=1):
            topic = item.get("topic", "other")
            severity = item.get("severity")
            res_type = item.get("resolution_type")
            score = item.get("score")
            codes = (item.get("findings") or {}).get("codes") or []
            narrative = (item.get("narrative") or {}).get("rendered_text")

            draw_line(f"{idx}. {topic}", bold=True)
            draw_line(f"Severity: {severity} | Resolution: {res_type} | Score: {score}")
            if codes:
                draw_line("Codes: " + ", ".join(codes))
            if narrative:
                for line in str(narrative).splitlines():
                    draw_line(line)
            y -= 6

    # Issue counts
    counts = (packet.get("issues") or {}).get("counts") or {}
    if counts:
        y -= 4
        draw_line("Issue Counts", bold=True)
        for k in ("high", "medium", "low", "total"):
            if k in counts:
                draw_line(f"{k.capitalize()}: {counts[k]}")

    c.save()
    return out
