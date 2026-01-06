# src/packet.py

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any, Dict, List, Literal, Optional, Tuple

from .pipeline import BuildResult
from .validate import Issue
from .glue import RawSnapshot


Severity = Literal["high", "medium", "low"]

# ======================================================
# Top Risk Summary (attorney-facing)
# ======================================================

RISK_WEIGHTS = {
    "travel_admission": 100,  # Missing I-94 / inspected / class of admission
    "travel_integrity": 35,   # Overlaps, missing pairings, contradictions
    "address_continuity": 70, # Gaps/overlaps in residence history
    "joint_residency": 50,    # Shared residence evidence issues
    "employment": 40,         # Employment continuity issues
    "formatting": 10,         # State code warnings, minor formatting
    "other": 20,              # fallback
}

SEVERITY_BUMP = {
    "high": 30,
    "medium": 15,
    "low": 5,
}

TOPIC_METADATA: Dict[str, Dict[str, Any]] = {
    "travel_admission": {
        "title": "Admission/Inspection Risk",
        "desc": (
            "AOS generally requires the applicant to have been inspected and admitted or paroled. "
            "Missing last-entry details (inspection, class of admission, I-94) can trigger RFEs or intensive questioning."
        ),
        "actions": [
            "Obtain the I-94 record for the most recent entry (electronic or paper).",
            "Confirm class of admission/status for the most recent entry.",
            "Confirm whether the applicant was inspected/admitted/paroled on the most recent entry.",
        ],
    },
    "travel_integrity": {
        "title": "Travel History Contradictions",
        "desc": (
            "Overlapping trips or unmatched entries/exits suggest the travel record may be incomplete or inconsistent. "
            "This can lead to RFEs or interview questions about presence in the U.S."
        ),
        "actions": [
            "Correct any overlapping travel dates (trips cannot overlap).",
            "Provide missing entry/exit dates so travel events are properly paired.",
            "Confirm whether the applicant is currently in the U.S. based on the most recent travel event.",
        ],
    },
    "address_continuity": {
        "title": "Gaps in U.S. Residence History",
        "desc": (
            "USCIS generally expects a complete residence history for the required period. "
            "Unexplained gaps or overlaps can trigger RFEs to clarify where the applicant lived."
        ),
        "actions": [
            "Fill any missing address periods with an address and dates.",
            "Clarify overlaps (primary residence vs temporary stay).",
            "Confirm start/end-of-window coverage for the required period.",
        ],
    },
    "joint_residency": {
        "title": "Shared Residence Evidence Needs Clarification",
        "desc": (
            "If no shared residence is detected (or only a loose match), USCIS may ask for clarification and additional evidence "
            "about the couple’s living arrangement."
        ),
        "actions": [
            "Confirm whether/when the couple lived together and provide the shared address and dates.",
            "Confirm unit/apartment and ZIP details if the match is only loose.",
            "Prepare a brief explanation if living separately for any period.",
        ],
    },
    "employment": {
        "title": "Employment Timeline Continuity",
        "desc": (
            "Employment gaps/overlaps can trigger follow-up questions and may require explanation or corrections on the forms."
        ),
        "actions": [
            "Fill missing employment periods (including unemployment) with dates.",
            "Clarify overlaps (multiple jobs vs incorrect dates).",
            "Confirm self-employment details (business name, dates, location).",
        ],
    },
    "formatting": {
        "title": "Formatting / Data Normalization",
        "desc": (
            "Minor formatting issues (e.g., state codes) are unlikely to be fatal but are worth correcting to avoid confusion."
        ),
        "actions": [
            "Normalize U.S. state to 2-letter code (e.g., NC).",
            "Confirm ZIP and unit formatting where applicable.",
        ],
    },
    "other": {
        "title": "Other Review Items",
        "desc": "Additional items that may require attorney review or clarification.",
        "actions": [],
    },
}


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def _cluster_max_severity(issues: List[Issue]) -> Severity:
    priority = {"high": 3, "medium": 2, "low": 1}
    return max(issues, key=lambda i: priority.get(i.severity, 0)).severity  # type: ignore


def _map_issue_to_topic(issue: Issue) -> str:
    """
    Stable, conservative topic mapper.

    Prefer issue.category (stable). Use message keywords only to split travel into:
      - travel_admission vs travel_integrity
    """
    cat = (issue.category or "").strip().lower()
    msg = (issue.message or "").lower()

    if cat == "travel":
        # Travel admission / inspection completeness (AOS-critical)
        # IMPORTANT: return TOPIC names here, not finding codes.
        if (
            "last entry" in msg
            or "i-94" in msg
            or "i94" in msg
            or "class of admission" in msg
            or "inspected" in msg
            or "admitted" in msg
            or "paroled" in msg
        ):
            return "travel_admission"

        # Everything else travel-related falls under integrity/completeness
        return "travel_integrity"

    if cat == "address_history":
        # Split formatting-ish address warnings into formatting
        if "2-letter state" in msg or "state codes" in msg or "prefers 2-letter" in msg:
            return "formatting"
        return "address_continuity"

    if cat == "joint_residency":
        return "joint_residency"

    if cat == "employment":
        return "employment"

    # Marriage/date etc. can be "other" for now
    return "other"


def _extract_finding_code(issue: Issue) -> Optional[str]:
    """
    Map Issue -> standardized finding code (stable output).
    Uses category + message patterns. Keep conservative and test-covered.
    """
    cat = (issue.category or "").strip().lower()
    msg = (issue.message or "").lower()

    # ---- Travel ----
    if cat == "travel":
            # ---- Last-entry specific (AOS-critical): MUST come BEFORE generic rules ----
        if "last entry" in msg and ("missing i-94" in msg or "missing i94" in msg):
            return "missing_i94_last_entry"
        if "last entry" in msg and ("missing class of admission" in msg or "missing class" in msg):
            return "missing_class_of_admission_last_entry"
        if "last entry" in msg and (
            ("missing whether you were inspected" in msg) or (("missing whether" in msg) and ("inspected" in msg))
        ):
            return "missing_inspection_flag_last_entry"
        if "last entry" in msg and ("not inspected" in msg or "indicates not inspected" in msg):
            return "not_inspected_last_entry"

        # ---- Generic admission fields (non-last-entry messages) ----
        if "missing i-94" in msg or "missing i94" in msg:
            return "missing_i94"
        if "missing class of admission" in msg or "missing class" in msg:
            return "missing_class_of_admission"
        if ("missing whether you were inspected" in msg) or (("missing whether" in msg) and ("inspected" in msg)):
            return "missing_inspection_flag"
        if "not inspected" in msg or "indicates not inspected" in msg:
            return "not_inspected"

        # ---- Integrity / pairing ----
        if "two entries in a row" in msg:
            return "double_entry"
        if "two exits in a row" in msg or "multiple exits" in msg:
            return "double_exit"
        if "exit recorded" in msg and "without a corresponding entry" in msg:
            return "unmatched_exit"
        if "entry recorded" in msg and "without a preceding exit" in msg:
            return "unmatched_entry"
        if "overlapping travel intervals" in msg:
            return "overlapping_travel_intervals"

        # ---- Absence duration ----
        if "extended time outside" in msg:
            return "long_absence_180_plus"
        if "significant time outside" in msg:
            return "long_absence_90_179"

        # ---- Travel vs employment overlap (note: your original condition looked inverted) ----
        if "overlaps an active" in msg and "employment" in msg:
            return "travel_overlaps_employment"
        
        if "first in-window travel event is an entry" in msg:
            return "baseline_entry_without_exit"

        return "travel_other"

    # ---- Address history ----
    if cat == "address_history":
        if "no residential addresses provided for the selected window" in msg:
            return "no_address_history_provided"
        if "no residential addresses overlap the required window" in msg:
            return "no_address_overlap_in_window"
        
        # Window coverage-specific gaps
        if "address gap at the start of the window" in msg:
            return "address_window_start_missing"
        if "address gap at the end of the window" in msg:
            return "address_window_end_missing"

        # Generic gaps/overlaps
        if "address gap" in msg or "unexplained address gap" in msg:
            return "address_gap"
        if "overlapping residential addresses" in msg or ("overlap" in msg and "addresses" in msg):
            return "address_overlap"
        
        if "prefers 2-letter state codes" in msg:
            return "state_code_formatting"
        if "missing required field" in msg and "street_name" in msg:
            return "missing_street"
        if "missing required field" in msg and "city" in msg:
            return "missing_city"
        if "missing required field" in msg and "country" in msg:
            return "missing_country"

        return "address_other"

    # ---- Joint residency ----
    if cat == "joint_residency":
        if "no shared residential address overlap" in msg:
            return "no_joint_residency_detected"
        if "only via loose address matching" in msg or "only loose" in msg:
            return "loose_joint_residency_match"
        return "joint_residency_other"

    # ---- Employment ----
    if cat == "employment":
        if "no employment history provided for the selected window" in msg:
            return "no_employment_history_provided"
        if "no employment entries overlap the required window" in msg:
            return "no_employment_overlap_in_window"

        # Window coverage gaps
        if "employment gap at the start of the window" in msg:
            return "employment_window_start_missing"
        if "employment gap at the end of the window" in msg:
            return "employment_window_end_missing"

        # Generic gaps
        if "unexplained employment gap" in msg or ("employment gap" in msg):
            return "employment_gap"

        # Overlaps (if you have that validator)
        if "overlapping employment" in msg or ("overlap" in msg and "employment" in msg):
            return "employment_overlap"

        return "employment_other"

    # ---- Marriage / date / other ----
    if cat == "marriage":
        if "invalid or unrecognized date" in msg:
            return "invalid_marriage_date"
        return "marriage_other"

    if cat == "date":
        return "invalid_date"

    return None


def _finding_counts(issues: List[Issue]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for i in issues:
        code = _extract_finding_code(i)
        if not code:
            continue
        counts[code] = counts.get(code, 0) + 1
    return counts


def _top_findings(counts: Dict[str, int], k: int = 3) -> List[str]:
    # Sort by frequency desc, then code name asc for stability
    return [c for c, _n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:k]]


def build_top_risk_summary(issues: List[Issue], n: int = 5) -> List[Dict[str, Any]]:
    """
    Cluster issues into attorney-friendly topics and rank them by risk score.
    Returns top N clusters.

    Scoring:
      score = base_topic_weight + severity_bump(max_severity) + small_count_factor
    """
    if not issues:
        return []

    clusters: Dict[str, List[Issue]] = {}
    for issue in issues:
        topic = _map_issue_to_topic(issue)
        clusters.setdefault(topic, []).append(issue)

    summary: List[Dict[str, Any]] = []

    for topic, topic_issues in clusters.items():
        max_sev = _cluster_max_severity(topic_issues)
        base_weight = RISK_WEIGHTS.get(topic, RISK_WEIGHTS["other"])
        bump = SEVERITY_BUMP.get(max_sev, 0)

        # Count factor: rewards many related issues but caps the effect
        count_factor = min(len(topic_issues) * 2, 20)

        total_score = base_weight + bump + count_factor

        meta = TOPIC_METADATA.get(topic, TOPIC_METADATA["other"])

        ref_ids = _dedupe_preserve_order(
            sorted([i.ref_id for i in topic_issues if i.ref_id])
        )

        suggested_questions = _dedupe_preserve_order(
            [q for q in (i.suggested_question for i in topic_issues) if q and q.strip()]
        )

        # Give 2 sample messages for context (attorney quickly sees what's inside)
        sample_messages = _dedupe_preserve_order([i.message for i in topic_issues if i.message])[:2]

        finding_counts = _finding_counts(topic_issues)
        finding_codes = sorted(finding_counts.keys())
        key_findings = _top_findings(finding_counts, k=3)


        summary.append(
            {
                "topic": topic,
                "title": meta.get("title", topic),
                "why_it_matters": meta.get("desc", ""),
                "action_items": meta.get("actions", []),
                "severity": max_sev,
                "score": total_score,
                "issue_count": len(topic_issues),
                "ref_ids": ref_ids,
                "suggested_questions": suggested_questions,
                "sample_messages": sample_messages,
                "findings": {
                    "codes": finding_codes,
                    "counts": finding_counts,
                    "key": key_findings,
                },
            }
        )

    # Rank by score (desc), then by severity (desc), then stable topic name
    sev_rank = {"high": 3, "medium": 2, "low": 1}
    summary.sort(key=lambda x: (x["score"], sev_rank.get(x["severity"], 0), x["topic"]), reverse=True)

    # Add rank numbers
    top = summary[:n]
    for idx, item in enumerate(top, start=1):
        item["rank"] = idx

    return top


def _bullet(lines: List[str]) -> str:
    return "\n".join([f"- {l}" for l in lines if l and str(l).strip()])


EVIDENCE_TARGETS: Dict[str, List[str]] = {
    "travel_admission": [
        "I-94 record (most recent entry)",
        "Passport biographic page",
        "Visa page (if applicable)",
        "Entry stamp / CBP admission record (if available)",
    ],
    "travel_integrity": [
        "Passport stamps",
        "Flight itinerary / boarding passes (if applicable)",
        "CBP travel history record (if available)",
    ],
    "address_continuity": [
        "Lease / mortgage statements",
        "Utility bills showing name/address",
        "Mail addressed to applicant at the residence",
        "Driver license / state ID address history (if applicable)",
    ],
    "joint_residency": [
        "Lease/mortgage showing both names",
        "Joint utility bills",
        "Joint bank statements",
        "Insurance policies showing both spouses",
        "Affidavits from friends/family (if needed)",
    ],
    "employment": [
        "Pay stubs",
        "W-2 / 1099 forms",
        "Employment verification letter",
        "Tax returns",
        "Business registration / invoices (for self-employment)",
    ],
    "formatting": [],
    "other": [],
}


def add_top_risk_narratives(
    risk_items: List[Dict[str, Any]],
    *,
    max_client_questions: int = 3,
    max_summary_points: int = 3,
) -> List[Dict[str, Any]]:
    """
    Enrich each top risk item with a structured 'narrative' object and a rendered_text view.
    This keeps structured fields as the source of truth while still enabling PDF/Markdown export.

    Enhancement:
      - If the risk item includes standardized findings (item["findings"]),
        the narrative will lead with "Key findings: ..." before sample messages.
      - Findings are stored explicitly in the structured narrative for UI/analytics stability.
    """
    enriched: List[Dict[str, Any]] = []

    for item in risk_items:
        topic = item.get("topic", "other")
        title = item.get("title", topic)

        why = item.get("why_it_matters") or ""
        actions = list(item.get("action_items") or [])
        ref_ids = list(item.get("ref_ids") or [])

        # Derived from issues
        sample_msgs = list(item.get("sample_messages") or [])[:max_summary_points]
        client_qs = list(item.get("suggested_questions") or [])[:max_client_questions]

        # Findings (standardized) if present
        findings = item.get("findings") or {}
        key_findings = list(findings.get("key") or [])
        finding_codes = list(findings.get("codes") or [])

        # Build summary points: key findings first, then sample messages
        summary_points: List[str] = []
        if key_findings:
            summary_points.append("Key findings: " + ", ".join(key_findings))
        summary_points.extend(sample_msgs)

        evidence = EVIDENCE_TARGETS.get(topic, [])

        narrative_obj: Dict[str, Any] = {
            "title": title,
            "topic": topic,
            "severity": item.get("severity"),
            "score": item.get("score"),
            "issue_count": item.get("issue_count"),
            "summary_points": summary_points,
            "why_it_matters": why,
            "action_items": actions,
            "client_questions": client_qs,
            "evidence_targets": evidence,
            "refs": ref_ids,
            # NEW: Findings explicitly stored (structured, stable)
            "finding_codes": finding_codes,
            "key_findings": key_findings,
        }

        # Rendered text (derived view)
        parts: List[str] = []
        parts.append(f"{title}")
        parts.append("")
        parts.append(
            f"Severity: {item.get('severity')} | Score: {item.get('score')} | Issue count: {item.get('issue_count')}"
        )
        parts.append("")

        if summary_points:
            parts.append("What we found:")
            parts.append(_bullet(summary_points))
            parts.append("")

        if why:
            parts.append("Why it matters:")
            parts.append(why.strip())
            parts.append("")

        if actions:
            parts.append("Recommended actions:")
            parts.append(_bullet(actions))
            parts.append("")

        if client_qs:
            parts.append("Client questions:")
            parts.append(_bullet(client_qs))
            parts.append("")

        if evidence:
            parts.append("Evidence/documents to consider:")
            parts.append(_bullet(evidence))
            parts.append("")

        if ref_ids:
            parts.append(f"Refs: {', '.join(ref_ids)}")

        narrative_obj["rendered_text"] = "\n".join(parts).strip()

        enriched.append({**item, "narrative": narrative_obj})

    return enriched


def _iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _snapshot_index(snapshots: List[RawSnapshot]) -> Dict[str, RawSnapshot]:
    return {s.id: s for s in snapshots}


def _issue_to_dict(issue: Issue, snapshot_by_id: Dict[str, RawSnapshot]) -> Dict[str, Any]:
    ref_id = issue.ref_id
    snap = snapshot_by_id.get(ref_id) if ref_id else None

    return {
        "severity": issue.severity,
        "category": issue.category,
        "ref_id": ref_id,
        "message": issue.message,
        "suggested_question": issue.suggested_question,
        "raw_snapshot": asdict(snap) if snap else None,
    }


def _format_address_entry(e) -> Dict[str, Any]:
    a = e.address
    return {
        "address": {
            "street_name": a.street_name,
            "unit_type": a.unit_type,
            "unit_number": a.unit_number,
            "city": a.city,
            "state_province": a.state_province,
            "zip_code": a.zip_code,
            "country": a.country,
        },
        "date_from": _iso(e.date_from),
        "from_precision": e.from_precision,
        "date_to": _iso(e.date_to),  # None means Present
        "to_precision": e.to_precision,
        "address_type": e.address_type,
        "notes": e.notes,
    }


def _format_employment_entry(e) -> Dict[str, Any]:
    addr = None
    if e.employer_address is not None:
        a = e.employer_address
        addr = {
            "street_name": a.street_name,
            "unit_type": a.unit_type,
            "unit_number": a.unit_number,
            "city": a.city,
            "state_province": a.state_province,
            "zip_code": a.zip_code,
            "country": a.country,
        }

    return {
        "employer": e.employer,
        "role": e.role,
        "employer_address": addr,
        "date_from": _iso(e.date_from),
        "date_to": _iso(e.date_to),  # None means Present
        "employment_type": e.employment_type,
        "notes": e.notes,
    }


def _format_travel_entry(e) -> Dict[str, Any]:
    return {
        "event_type": e.event_type,
        "date": _iso(e.date),
        "port_or_city": e.port_or_city,
        "status_or_class": e.status_or_class,
        "notes": e.notes,
    }


def _group_issues(issues: List[Issue]) -> Dict[Severity, List[Issue]]:
    grouped: Dict[Severity, List[Issue]] = {"high": [], "medium": [], "low": []}
    for i in issues:
        grouped[i.severity].append(i)
    return grouped


def _group_issues_by_ref(issues: List[Issue]) -> Dict[str, List[Issue]]:
    by_ref: Dict[str, List[Issue]] = {}
    for i in issues:
        key = i.ref_id or "unlinked"
        by_ref.setdefault(key, []).append(i)
    return by_ref

def _group_issues_by_category(issues: List[Issue]) -> Dict[str, List[Issue]]:
    by_cat: Dict[str, List[Issue]] = {}
    for i in issues:
        by_cat.setdefault(i.category, []).append(i)
    return by_cat


def _top_issues(issues: List[Issue], n: int = 3) -> List[Issue]:
    # Prioritize high > medium > low, then keep original order
    priority = {"high": 0, "medium": 1, "low": 2}
    return sorted(issues, key=lambda x: priority.get(x.severity, 9))[:n]

def _format_joint_residency_window(w) -> Dict[str, Any]:
    return {
        "start": _iso(w.start),
        "end": _iso(w.end),
        "match_type": w.match_type,
        "petitioner_address": {
            "street_name": w.petitioner_entry.address.street_name,
            "unit_type": w.petitioner_entry.address.unit_type,
            "unit_number": w.petitioner_entry.address.unit_number,
            "city": w.petitioner_entry.address.city,
            "state_province": w.petitioner_entry.address.state_province,
            "zip_code": w.petitioner_entry.address.zip_code,
            "country": w.petitioner_entry.address.country,
        },
        "beneficiary_address": {
            "street_name": w.beneficiary_entry.address.street_name,
            "unit_type": w.beneficiary_entry.address.unit_type,
            "unit_number": w.beneficiary_entry.address.unit_number,
            "city": w.beneficiary_entry.address.city,
            "state_province": w.beneficiary_entry.address.state_province,
            "zip_code": w.beneficiary_entry.address.zip_code,
            "country": w.beneficiary_entry.address.country,
        },
    }

def _format_travel_interval(i) -> Dict[str, Any]:
    return {
        "exit_date": _iso(i.exit_date),
        "entry_date": _iso(i.entry_date),
        "days_abroad": i.days_abroad,
        "is_brief": i.is_brief,
    }


def build_attorney_review_packet(result: BuildResult) -> Dict[str, Any]:
    """
    Build a machine-friendly "attorney review packet" dict.

    Output includes:
      - window used for validation
      - marriage anchor fields (if present)
      - clean timelines (addresses/employment/travel) for beneficiary + petitioner
      - issues grouped by severity + also grouped by ref_id
      - raw snapshots available for every ref_id (when applicable)

    No new validation is performed here.
    """
    snap_by_id = _snapshot_index(result.snapshots)

    grouped_by_sev = _group_issues(result.issues)
    grouped_by_cat = _group_issues_by_category(result.issues)
    top = _top_issues(result.issues, n=3)

    top_risk_items = build_top_risk_summary(result.issues, n=5)
    top_risk_items = add_top_risk_narratives(top_risk_items)

    # Timelines
    beneficiary = result.case.beneficiary
    petitioner = result.case.petitioner

    packet: Dict[str, Any] = {
        "meta": {
            "window_start": _iso(result.window_start),
            "window_end": _iso(result.window_end),
        },
        "case": {
            "marriage": {
                "date": _iso(result.case.marriage_date),
                "city": result.case.marriage_city,
                "state_province": result.case.marriage_state_province,
                "country": result.case.marriage_country,
            }
        },
        "timelines": {
            "beneficiary": {
                "addresses_lived": [_format_address_entry(e) for e in beneficiary.addresses_lived],
                "employment": [_format_employment_entry(e) for e in beneficiary.employment],
                "travel": [_format_travel_entry(e) for e in beneficiary.travel_entries],
            },
            "petitioner": {
                "addresses_lived": [_format_address_entry(e) for e in petitioner.addresses_lived],
                "employment": [_format_employment_entry(e) for e in petitioner.employment],
                "travel": [_format_travel_entry(e) for e in petitioner.travel_entries],
            },
        },
        "joint_residency": {
            "first_shared_date": _iso(result.joint_residency.first_shared_date),
            "match_type": result.joint_residency.match_type,
            "windows": [
                _format_joint_residency_window(w)
                for w in result.joint_residency.windows
            ],
        },
        "top_risks": {
            "items": top_risk_items,
        },
        "issues": {
            "summary": {
                "total": len(result.issues),
                "counts_by_severity": {
                    "high": len(grouped_by_sev["high"]),
                    "medium": len(grouped_by_sev["medium"]),
                    "low": len(grouped_by_sev["low"]),
                },
                "top_items": [
                    {
                        "severity": i.severity,
                        "category": i.category,
                        "ref_id": i.ref_id,
                        "message": i.message,
                        "suggested_question": i.suggested_question,
                    }
                    for i in top
                ],
            },
            "counts": {
                "high": len(grouped_by_sev["high"]),
                "medium": len(grouped_by_sev["medium"]),
                "low": len(grouped_by_sev["low"]),
                "total": len(result.issues),
            },
            "by_severity": {
                "high": [_issue_to_dict(i, snap_by_id) for i in grouped_by_sev["high"]],
                "medium": [_issue_to_dict(i, snap_by_id) for i in grouped_by_sev["medium"]],
                "low": [_issue_to_dict(i, snap_by_id) for i in grouped_by_sev["low"]],
            },
            "by_category": {
                cat: [_issue_to_dict(i, snap_by_id) for i in cat_issues]
                for cat, cat_issues in grouped_by_cat.items()
            },
            "by_ref_id": {
                ref_id: [_issue_to_dict(i, snap_by_id) for i in issues_for_ref]
                for ref_id, issues_for_ref in _group_issues_by_ref(result.issues).items()
            },
        },
        "travel_analysis": {
            "beneficiary": {
                "inferred_in_us": result.travel_beneficiary.inferred_in_us,
                "last_event_type": result.travel_beneficiary.last_event_type,
                "last_event_date": _iso(result.travel_beneficiary.last_event_date),
                "intervals": [_format_travel_interval(i) for i in result.travel_beneficiary.intervals],
            },
            "petitioner": {
                "inferred_in_us": result.travel_petitioner.inferred_in_us,
                "last_event_type": result.travel_petitioner.last_event_type,
                "last_event_date": _iso(result.travel_petitioner.last_event_date),
                "intervals": [_format_travel_interval(i) for i in result.travel_petitioner.intervals],
            },
        },
        # Optional: include snapshots as a flat list too (useful for UI/debug)
        "raw_snapshots": [asdict(s) for s in result.snapshots],
    }

    return packet
