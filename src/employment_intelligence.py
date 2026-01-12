# src/employment_intelligence.py

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional, Tuple, Literal, Set

from .models import EmploymentEntry, DatePrecision
from .travel_intelligence import TravelInterval
from .validate import Issue


PersonRole = Literal["beneficiary", "petitioner"]


def _last_day_of_month(y: int, m: int) -> date:
    if m == 12:
        return date(y, 12, 31)
    return date(y, m + 1, 1) - timedelta(days=1)


def _precision_range_start(d: date, precision: DatePrecision) -> date:
    if precision == "day":
        return d
    if precision == "month":
        return date(d.year, d.month, 1)
    # year
    return date(d.year, 1, 1)


def _precision_range_end(d: date, precision: DatePrecision) -> date:
    if precision == "day":
        return d
    if precision == "month":
        return _last_day_of_month(d.year, d.month)
    # year
    return date(d.year, 12, 31)


def _build_employment_ranges(
    employment: List[EmploymentEntry],
    *,
    window_start: date,
    window_end: date,
) -> List[Tuple[date, date, EmploymentEntry]]:
    """Build precision-aware employment ranges, clamped to window."""
    ranges: List[Tuple[date, date, EmploymentEntry]] = []

    for e in employment:
        start = _precision_range_start(e.date_from, e.from_precision)

        effective_end = e.date_to or window_end
        end_precision: DatePrecision = e.to_precision if e.date_to is not None else "day"
        end = _precision_range_end(effective_end, end_precision)

        if end < window_start or start > window_end:
            continue

        ranges.append((max(start, window_start), min(end, window_end), e))

    ranges.sort(key=lambda x: (x[0], x[1]))
    return ranges


def _ranges_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return max(a_start, b_start) <= min(a_end, b_end)


def analyze_employment_authorization(
    *,
    role: PersonRole,
    employment: List[EmploymentEntry],
    travel_intervals: List[TravelInterval],
    window_start: date,
    window_end: date,
) -> List[Issue]:
    """Employment + travel intelligence.

    Goals (conservative, non-accusatory):
    - Detect employment that appears active during long absences (>=90 days).
    - For the beneficiary only, add an additional clarification flag when the absence is very long (>=180 days)
      and employment overlaps, framed as "may require explanation/evidence" (not an accusation).

    Output:
    - Issues in the "employment" category (MEDIUM severity) to keep clustering consistent.
    """

    if not employment or not travel_intervals:
        return []

    emp_ranges = _build_employment_ranges(employment, window_start=window_start, window_end=window_end)
    if not emp_ranges:
        return []

    issues: List[Issue] = []

    for interval in travel_intervals:
        if interval.is_brief:
            continue
        if interval.days_abroad < 90:
            continue

        absent_start = max(interval.exit_date, window_start)
        absent_end = min(interval.entry_date, window_end)
        if absent_end < absent_start:
            continue

        overlapping_employers: Set[str] = set()
        for e_start, e_end, e in emp_ranges:
            if _ranges_overlap(absent_start, absent_end, e_start, e_end):
                if e.employer:
                    overlapping_employers.add(e.employer)
                else:
                    overlapping_employers.add("(unknown employer)")

        if not overlapping_employers:
            continue

        employers_txt = ", ".join(sorted(overlapping_employers))
        issues.append(
            Issue(
                severity="medium",
                category="employment",
                message=(
                    "Employment appears active during time outside the U.S. "
                    f"from {absent_start.isoformat()} to {absent_end.isoformat()} "
                    f"({interval.days_abroad} days). Employers: {employers_txt}. "
                    "Please clarify (e.g., were you on leave, working remotely, or are the dates inaccurate?)."
                ),
            )
        )

        # Beneficiary-only: additional "clarify risk" flag for very long absences.
        if role == "beneficiary" and interval.days_abroad >= 180:
            issues.append(
                Issue(
                    severity="medium",
                    category="employment",
                    message=(
                        "Beneficiary employment recorded during an extended absence (180+ days) "
                        f"from {absent_start.isoformat()} to {absent_end.isoformat()}. "
                        "This may require clarification or evidence regarding work authorization "
                        "(for example: no work performed, remote work outside the U.S., or EAD timing)."
                    ),
                )
            )

    return issues
