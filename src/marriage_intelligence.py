# src/marriage_intelligence.py

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from .models import ImmigrationCase
from .joint_residency import JointResidencyResult
from .travel_intelligence import TravelAnalysisResult
from .validate import Issue


def _overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return max(a_start, b_start) <= min(a_end, b_end)


def _fmt(d: date) -> str:
    return d.isoformat()


def analyze_marriage_timeline(
    case: ImmigrationCase,
    *,
    joint_residency: JointResidencyResult,
    travel_beneficiary: TravelAnalysisResult,
    travel_petitioner: TravelAnalysisResult,
    window_start: date,
    window_end: date,
    near_days: int = 180,
) -> List[Issue]:
    """Marriage timeline intelligence (evidence planning + clarification).

    Conservative, non-judgmental checks intended to reduce RFEs and limit back-and-forth:
      - Marriage date vs shared residence windows: if no shared window is detected near
        the marriage date, suggest preparing an explanation/evidence.
      - Marriage date vs long separations (travel intervals): if either spouse has a
        long travel absence (>=90 days) near/after marriage, suggest preparing an
        explanation/evidence.

    Notes:
      - This is NOT a "bona fide" determination.
      - Outputs are MEDIUM severity, framed as planning prompts.
    """

    mdate: Optional[date] = case.marriage_date
    if mdate is None:
        return []

    # Only reason over marriage date when it lies within the selected window.
    if mdate < window_start or mdate > window_end:
        return []

    issues: List[Issue] = []

    near_start = max(window_start, mdate - timedelta(days=near_days))
    near_end = min(window_end, mdate + timedelta(days=near_days))

    # ----------------------
    # Shared residence near marriage
    # ----------------------
    has_shared_near_marriage = False
    for w in joint_residency.windows:
        if _overlap(w.start, w.end, near_start, near_end):
            has_shared_near_marriage = True
            break

    if not has_shared_near_marriage:
        issues.append(
            Issue(
                severity="medium",
                category="marriage",
                ref_id="marriage_timeline",
                message=(
                    "No shared residential address overlap was detected around the marriage date "
                    f"({_fmt(near_start)} to {_fmt(near_end)})."
                ),
                suggested_question=(
                    "After you got married, did you live together (or maintain a shared primary residence)? "
                    "If yes, please provide the shared address and dates. If no, please briefly explain the living "
                    "arrangement (e.g., work/school, temporary separation) and provide any supporting context."
                ),
            )
        )

    # ----------------------
    # Long travel separations near marriage (post-marriage emphasis)
    # ----------------------
    post_start = mdate
    post_end = min(window_end, mdate + timedelta(days=near_days))

    long_absence_threshold = 90

    def _long_absences_near(travel: TravelAnalysisResult) -> List[str]:
        hits: List[str] = []
        for it in travel.intervals:
            if it.is_brief:
                continue
            if it.days_abroad < long_absence_threshold:
                continue
            if _overlap(it.exit_date, it.entry_date, post_start, post_end):
                hits.append(f"{_fmt(it.exit_date)} to {_fmt(it.entry_date)} ({it.days_abroad} days)")
        return hits

    ben_hits = _long_absences_near(travel_beneficiary)
    pet_hits = _long_absences_near(travel_petitioner)

    if ben_hits or pet_hits:
        parts: List[str] = []
        if ben_hits:
            parts.append("Beneficiary travel: " + "; ".join(ben_hits))
        if pet_hits:
            parts.append("Petitioner travel: " + "; ".join(pet_hits))

        issues.append(
            Issue(
                severity="medium",
                category="marriage",
                ref_id="marriage_timeline",
                message=(
                    "Extended travel separation was detected near the marriage date "
                    f"({post_start.isoformat()} to {post_end.isoformat()}). "
                    + " ".join(parts)
                ),
                suggested_question=(
                    "Were you living together and maintaining the relationship during these periods? "
                    "If these dates are correct, consider preparing a brief explanation and supporting evidence "
                    "(e.g., travel records, communications, visits, joint finances, plans to reunite)."
                ),
            )
        )

    return issues
