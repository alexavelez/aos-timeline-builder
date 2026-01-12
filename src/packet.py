# src/packet.py

from __future__ import annotations

from dataclasses import asdict
from datetime import date
import re
from typing import Any, Dict, List, Literal, Optional, Tuple

from .pipeline import BuildResult
from .validate import Issue
from .glue import RawSnapshot


Severity = Literal["high", "medium", "low"]
ResolutionType = Literal["must_fix", "explain", "prepare_evidence"]
ExecutiveRole = Literal["beneficiary", "petitioner", "both", "case"]

# ======================================================
# Packet schema stabilization (productization)
# ======================================================

# Increment when the *output packet structure* changes in a backward-incompatible way.
# Keep this stable once clients depend on it.
PACKET_SCHEMA_VERSION = "0.3.2"

# Freeze resolution types for product stability.
ALLOWED_RESOLUTION_TYPES: Tuple[ResolutionType, ...] = (
    "must_fix",
    "explain",
    "prepare_evidence",
)

# Freeze executive summary roles for product stability.
ALLOWED_EXECUTIVE_ROLES: Tuple[ExecutiveRole, ...] = (
    "beneficiary",
    "petitioner",
    "both",
    "case",
)

# ======================================================
# Top Risk Summary (attorney-facing)
# ======================================================

RISK_WEIGHTS = {
    "travel_admission": 100,  # Missing I-94 / inspected / class of admission
    "travel_integrity": 35,   # Overlaps, missing pairings, contradictions
    "address_continuity": 70, # Gaps/overlaps in residence history
    "joint_residency": 50,    # Shared residence evidence issues
    "employment": 40,         # Employment continuity issues
    "marriage": 30,           # Evidence planning prompts near marriage date
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
    "marriage": {
        "title": "Marriage Timeline Evidence Planning",
        "desc": (
            "Timeline patterns near the marriage date can lead to follow-up questions. "
            "These prompts help attorneys plan explanations and evidence proactively, without making any legal conclusions."
        ),
        "actions": [
            "Confirm living arrangement near/after the marriage date.",
            "If separated for work/school/travel, prepare a brief explanation.",
            "Gather supporting evidence (communications, visits, joint finances, plans to reunite) as needed.",
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

# Freeze topic names for product stability.
ALLOWED_TOPIC_NAMES: Tuple[str, ...] = tuple(sorted(TOPIC_METADATA.keys()))


# Freeze finding codes for product stability. These are used downstream for:
# - clustering and ranking
# - analytics
# - UI filters
# - templated narratives
FINDING_CODE_REGISTRY: Tuple[str, ...] = (
    # Travel: last entry / admission fields
    "missing_i94_last_entry",
    "missing_class_of_admission_last_entry",
    "missing_inspection_flag_last_entry",
    "not_inspected_last_entry",

    # Travel: generic admission fields
    "missing_i94",
    "missing_class_of_admission",
    "missing_inspection_flag",
    "not_inspected",

    # Travel: integrity / pairing
    "double_entry",
    "double_exit",
    "unmatched_exit",
    "unmatched_entry",
    "overlapping_travel_intervals",
    "travel_overlaps_employment",
    "baseline_entry_without_exit",
    "travel_other",

    # Travel: absence duration
    "long_absence_180_plus",
    "long_absence_90_179",

    # Address history
    "no_address_history_provided",
    "no_address_overlap_in_window",
    "address_window_start_missing",
    "address_window_end_missing",
    "address_gap",
    "address_overlap",
    "state_code_formatting",
    "missing_street",
    "missing_city",
    "missing_country",
    "address_other",

    # Employment
    "no_employment_history_provided",
    "no_employment_overlap_in_window",
    "employment_window_start_missing",
    "employment_window_end_missing",
    "employment_gap",
    "employment_overlap",
    "employment_during_long_absence",
    "possible_unauthorized_work_risk",
    "employment_other",

    # Joint residency
    "no_joint_residency_detected",
    "loose_joint_residency_match",
    "joint_residency_other",

    # Marriage / date
    "no_shared_residence_near_marriage",
    "long_separation_near_marriage",
    "invalid_marriage_date",
    "marriage_other",
    "invalid_date",
)


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

    if cat == "marriage":
        return "marriage"

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
        # Employment + long-absence intelligence
        if "employment appears active during time outside" in msg or "active during time outside" in msg:
            return "employment_during_long_absence"
        if "work authorization" in msg or "possible unauthorized" in msg or "unauthorized work" in msg:
            return "possible_unauthorized_work_risk"

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
        if "no shared residential address overlap" in msg and "around the marriage date" in msg:
            return "no_shared_residence_near_marriage"
        if "extended travel separation" in msg and "near the marriage date" in msg:
            return "long_separation_near_marriage"
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


def _resolution_type_for_cluster(
    *,
    topic: str,
    max_severity: Severity,
    finding_codes: List[str],
) -> ResolutionType:
    """Recommend what the attorney/paralegal should do with this risk cluster.

    - must_fix: missing/contradictory data that needs correction or completion
    - explain: facts may be accurate but should be explained in narrative or at interview
    - prepare_evidence: facts may be accurate but typically require evidence planning

    Conservative policy: high severity defaults to must_fix unless the finding implies
    a legal/factual constraint that can't be "fixed" (e.g., not inspected).
    """

    codes = set(finding_codes or [])

    # Findings that imply a legal/factual constraint (cannot be "fixed" by editing data).
    evidence_driven_codes = {
        "not_inspected_last_entry",
        "not_inspected",
        # Employment authorization / compliance is typically evidence/explanation driven.
        "possible_unauthorized_work_risk",

        # Marriage timeline prompts (evidence planning)
        "no_shared_residence_near_marriage",
        "long_separation_near_marriage",
    }

    # Findings that are almost always data-completion items.
    must_fix_codes = {
        # Address window coverage / missing history
        "no_address_history_provided",
        "no_address_overlap_in_window",
        "address_window_start_missing",
        "address_window_end_missing",
        "address_gap",
        "address_overlap",

        # Employment window coverage / missing history
        "no_employment_history_provided",
        "no_employment_overlap_in_window",
        "employment_window_start_missing",
        "employment_window_end_missing",
        "employment_gap",
        "employment_overlap",

        # Travel integrity
        "double_entry",
        "double_exit",
        "unmatched_exit",
        "unmatched_entry",
        "overlapping_travel_intervals",
        "travel_overlaps_employment",

        # Joint residency needs confirmation to resolve
        "loose_joint_residency_match",
    }

    # Travel admission fields: typically must collect data/evidence.
    admission_missing_codes = {
        "missing_i94_last_entry",
        "missing_class_of_admission_last_entry",
        "missing_inspection_flag_last_entry",
        "missing_i94",
        "missing_class_of_admission",
        "missing_inspection_flag",
    }

    # Topic-based defaults
    if codes & evidence_driven_codes:
        return "prepare_evidence"

    # Employment + travel consistency: typically explain (not a "fix" unless dates are wrong).
    if "employment_during_long_absence" in codes:
        return "explain"

    if topic in {"address_continuity", "employment"}:
        # These are primarily completeness/correction tasks.
        return "must_fix" if max_severity in {"high", "medium"} else "explain"

    if topic == "travel_admission":
        if codes & admission_missing_codes:
            return "must_fix"
        return "prepare_evidence"

    if topic == "travel_integrity":
        # Baseline entry without exit is often outside-window and may not be fixable.
        if codes == {"baseline_entry_without_exit"}:
            return "explain"
        if codes & must_fix_codes:
            return "must_fix"
        return "explain"

    if topic == "joint_residency":
        # If no joint residency is detected, often requires evidence planning or explanation.
        if "no_joint_residency_detected" in codes:
            return "prepare_evidence"
        if "loose_joint_residency_match" in codes:
            return "must_fix"
        return "explain"

    if topic == "formatting":
        return "must_fix"

    # Fallback: high/medium -> must_fix, low -> explain
    return "must_fix" if max_severity in {"high", "medium"} else "explain"


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

        resolution_type = _resolution_type_for_cluster(
            topic=topic,
            max_severity=max_sev,
            finding_codes=finding_codes,
        )


        summary.append(
            {
                "topic": topic,
                "title": meta.get("title", topic),
                "why_it_matters": meta.get("desc", ""),
                "action_items": meta.get("actions", []),
                "resolution_type": resolution_type,
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


# ======================================================
# Client Clarification Pack (copy/paste ready)
# ======================================================



_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2}


def _who_from_ref_id(ref_id: Optional[str]) -> Optional[str]:
    if not ref_id:
        return None
    if ref_id.startswith('ben_'):
        return 'beneficiary'
    if ref_id.startswith('pet_'):
        return 'petitioner'
    if ref_id.startswith('case_'):
        return 'case'
    return None


def _client_topic_from_issue(issue: Issue) -> str:
    cat = (issue.category or '').strip().lower()
    if cat == 'address_history':
        return 'address'
    if cat == 'employment':
        return 'employment'
    if cat == 'travel':
        return 'travel'
    if cat == 'joint_residency':
        return 'joint_residency'
    if cat == 'marriage':
        return 'marriage'
    return 'other'


def _extract_iso_dates(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract up to two ISO dates (YYYY-MM-DD) from a string."""
    if not text:
        return (None, None)
    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if not dates:
        return (None, None)
    if len(dates) == 1:
        return (dates[0], dates[0])
    return (dates[0], dates[1])


def _priority_for_issue(issue: Issue) -> str:
    """Return P0/P1/P2 priority for client-facing clarification."""
    sev = (issue.severity or 'low').lower()
    code = _extract_finding_code(issue) or ''

    # Always P0 if high severity
    if sev == 'high':
        return 'P0'

    # Specific medium items we still want in the first client email
    P0_CODES = {
        'missing_i94_last_entry',
        'missing_class_of_admission_last_entry',
        'missing_inspection_flag_last_entry',
        'not_inspected_last_entry',
        'address_window_start_missing',
        'address_window_end_missing',
        'employment_window_start_missing',
        'employment_window_end_missing',
        'no_address_history_provided',
        'no_address_overlap_in_window',
        'no_employment_history_provided',
        'no_employment_overlap_in_window',
    }
    if code in P0_CODES:
        return 'P0'

    if sev == 'medium':
        return 'P1'

    return 'P2'


def build_client_clarification_pack(issues: List[Issue]) -> Dict[str, Any]:
    """Build a prioritized, deduplicated set of copy/paste-ready client questions."""
    # Only issues with actionable questions
    actionable = [i for i in issues if i.suggested_question and i.suggested_question.strip()]
    if not actionable:
        return {
            'summary': {
                'total_questions': 0,
                'by_topic': {},
                'by_priority': {'P0': 0, 'P1': 0, 'P2': 0},
            },
            'email': {
                'subject': 'A few final questions to complete your immigration forms',
                'body': 'No additional questions at this time.',
            },
            'questions': [],
        }

    # Deduplicate while preserving "best" (highest priority) version
    dedup: Dict[Tuple, Dict[str, Any]] = {}
    order: List[Tuple] = []

    for idx, issue in enumerate(actionable):
        who = _who_from_ref_id(issue.ref_id) or 'unknown'
        topic = _client_topic_from_issue(issue)
        prompt = (issue.suggested_question or '').strip()
        d1, d2 = _extract_iso_dates(prompt + ' ' + (issue.message or ''))
        key = (who, topic, d1, d2, prompt.lower())

        item = {
            'question_id': f"q_{idx}",
            'priority': _priority_for_issue(issue),
            'topic': topic,
            'who': who,
            'date_range': {'from': d1, 'to': d2} if d1 else None,
            'prompt': prompt,
            'source_refs': [issue.ref_id] if issue.ref_id else [],
            'derived_from': {
                'severity': issue.severity,
                'category': issue.category,
                'message': issue.message,
                'finding_code': _extract_finding_code(issue),
            },
        }

        if key not in dedup:
            dedup[key] = item
            order.append(key)
        else:
            # Keep the higher-priority one
            existing = dedup[key]
            if _PRIORITY_RANK[item['priority']] < _PRIORITY_RANK[existing['priority']]:
                dedup[key] = item
            # Merge refs
            existing_refs = set(existing.get('source_refs', []))
            for r in item.get('source_refs', []):
                existing_refs.add(r)
            existing['source_refs'] = sorted(existing_refs)

    questions = [dedup[k] for k in order]

    # Sort for output: P0 then P1 then P2, stable within each group
    questions = sorted(questions, key=lambda q: (_PRIORITY_RANK.get(q['priority'], 9), ))

    # Summary counts
    by_topic: Dict[str, int] = {}
    by_priority = {'P0': 0, 'P1': 0, 'P2': 0}
    for q in questions:
        by_topic[q['topic']] = by_topic.get(q['topic'], 0) + 1
        by_priority[q['priority']] += 1

    # Build email body (copy/paste)
    lines: List[str] = []
    lines.append('Hi,')
    lines.append('')
    lines.append('We’re preparing your forms and need a few final details so we can complete everything in one pass.')
    lines.append('Please reply with the information requested below (you can answer directly in this email).')
    lines.append('')

    # Group by topic then who
    def _topic_title(t: str) -> str:
        return {
            'address': 'Address history',
            'employment': 'Employment history',
            'travel': 'Travel history',
            'joint_residency': 'Living together (marriage)',
            'marriage': 'Marriage details',
            'other': 'Other',
        }.get(t, t)

    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for q in questions:
        grouped.setdefault((q['topic'], q['who']), []).append(q)

    # Topic order for nicer emails
    topic_order = ['address', 'employment', 'travel', 'joint_residency', 'marriage', 'other']

    for topic in topic_order:
        subkeys = [k for k in grouped.keys() if k[0] == topic]
        if not subkeys:
            continue
        lines.append(_topic_title(topic) + ':')
        for _t, who in sorted(subkeys, key=lambda x: x[1]):
            qs = grouped[(_t, who)]
            if who != 'unknown' and who != 'case':
                lines.append(f"- {who.capitalize()}:")
                for q in qs:
                    prefix = '  *'
                    if q['priority'] == 'P0':
                        prefix = '  * [REQUIRED]'
                    lines.append(f"{prefix} {q['prompt']}")
            else:
                for q in qs:
                    prefix = '*'
                    if q['priority'] == 'P0':
                        prefix = '* [REQUIRED]'
                    lines.append(f"{prefix} {q['prompt']}")
        lines.append('')

    lines.append('Thank you!')

    return {
        'summary': {
            'total_questions': len(questions),
            'by_topic': by_topic,
            'by_priority': by_priority,
        },
        'email': {
            'subject': 'A few final questions to complete your immigration forms',
            'body': "\n".join(lines).strip(),
        },
        'questions': questions,
    }


# ======================================================
# Executive Summary (page 1 for PDF; lawyer-first)
# ======================================================


def _role_from_ref_ids(ref_ids: List[str]) -> ExecutiveRole:
    """Infer who the item applies to using its ref_ids.

    We keep this intentionally conservative and deterministic.
    """

    who_set = set()
    for ref in ref_ids or []:
        w = _who_from_ref_id(ref)
        if w in ("beneficiary", "petitioner", "case"):
            who_set.add(w)

    if "beneficiary" in who_set and "petitioner" in who_set:
        return "both"
    if "beneficiary" in who_set:
        return "beneficiary"
    if "petitioner" in who_set:
        return "petitioner"
    return "case"


def build_executive_summary(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Build a lawyer-first executive summary.

    This is aggregation + formatting only. It must never omit details elsewhere.
    """

    meta = packet.get("meta", {}) or {}
    top_items = (packet.get("top_risks", {}) or {}).get("items", []) or []
    top5 = top_items[:5]

    exec_risks: List[Dict[str, Any]] = []
    severities = []
    evidence_topics: List[str] = []

    for item in top5:
        ref_ids = item.get("ref_ids") or []
        role = _role_from_ref_ids(list(ref_ids))
        narrative = (item.get("narrative") or {}).get("rendered_text")

        exec_risks.append(
            {
                "rank": item.get("rank"),
                "topic": item.get("topic"),
                "title": item.get("title"),
                "role": role,
                "severity": item.get("severity"),
                "resolution_type": item.get("resolution_type"),
                "finding_codes": ((item.get("findings") or {}).get("codes") or []),
                "summary": (str(narrative).strip() if narrative else None),
            }
        )

        if item.get("severity"):
            severities.append(item["severity"])
        if item.get("resolution_type") == "prepare_evidence":
            title = item.get("title") or item.get("topic")
            if title:
                evidence_topics.append(str(title))

    # Client follow-up snapshot
    ccp = packet.get("client_clarification_pack") or {}
    ccp_summary = ccp.get("summary") or {}
    by_priority = ccp_summary.get("by_priority") or {}
    p0 = int(by_priority.get("P0", 0))
    p1 = int(by_priority.get("P1", 0))

    blocking_topics: List[str] = []
    for q in (ccp.get("questions") or []):
        if q.get("priority") == "P0":
            t = q.get("topic")
            if t:
                blocking_topics.append(str(t))
    blocking_topics = _dedupe_preserve_order(blocking_topics)

    # Overall risk posture (mechanical)
    posture: str
    if any(s == "high" for s in severities):
        posture = "elevated"
    elif any(s == "medium" for s in severities):
        posture = "moderate"
    else:
        posture = "low"

    return {
        "schema_version": meta.get("schema_version"),
        "window_start": meta.get("window_start"),
        "window_end": meta.get("window_end"),
        "top_risks": exec_risks,
        "client_followup": {
            "required_p0": p0,
            "recommended_p1": p1,
            "blocking_topics": blocking_topics,
        },
        "evidence_planning": {
            "items": _dedupe_preserve_order(evidence_topics),
        },
        "overall_risk_posture": posture,
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
            "schema_version": PACKET_SCHEMA_VERSION,
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
        "client_clarification_pack": build_client_clarification_pack(result.issues),
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

    # Executive summary is lawyer-first and used as page 1 in exports.
    packet["executive_summary"] = build_executive_summary(packet)

    return packet
