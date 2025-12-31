# src/packet.py

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any, Dict, List, Literal, Optional, Tuple

from .pipeline import BuildResult
from .validate import Issue
from .glue import RawSnapshot


Severity = Literal["high", "medium", "low"]


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
        # Optional: include snapshots as a flat list too (useful for UI/debug)
        "raw_snapshots": [asdict(s) for s in result.snapshots],
    }

    return packet
