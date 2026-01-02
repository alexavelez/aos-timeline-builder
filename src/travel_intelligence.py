# src/travel_intelligence.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Literal, Tuple

from .models import TravelEntry, EmploymentEntry, DatePrecision
from .validate import Issue


@dataclass(frozen=True)
class TravelInterval:
    exit_date: date
    entry_date: date
    days_abroad: int
    is_brief: bool  # same-day (often <24h trips are same calendar day in intakes)


@dataclass(frozen=True)
class TravelAnalysisResult:
    intervals: List[TravelInterval]
    issues: List[Issue]
    last_event_type: Optional[Literal["entry", "exit"]]
    last_event_date: Optional[date]
    inferred_in_us: Optional[bool]  # True=in US, False=outside US, None=unknown


# -------------------------
# Precision helpers (aligned with validate.py patterns)
# -------------------------

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
    """
    Build precision-aware employment ranges, clamped to window.
    Assumes EmploymentEntry has from_precision/to_precision (as in your employment gaps/overlaps work).
    """
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


def _days_inclusive(d1: date, d2: date) -> int:
    return (d2 - d1).days + 1


def _ranges_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return max(a_start, b_start) <= min(a_end, b_end)


def analyze_travel(
    travel_entries: List[TravelEntry],
    *,
    window_start: date,
    window_end: date,
    employment: Optional[List[EmploymentEntry]] = None,
) -> TravelAnalysisResult:
    """
    Travel Pairer + intelligence (AOS-oriented, conservative).

    Core:
      - Pair each EXIT with the next ENTRY => TravelInterval
      - Same-day exit+entry => is_brief=True (do NOT trigger long-absence scrutiny)

    Integrity / RFE-risk flags (conservative):
      - EXIT without following ENTRY => HIGH
      - ENTRY without preceding EXIT:
          * first in-window event is ENTRY => LOW baseline-note (exit may be outside window)
          * otherwise => HIGH
      - Two EXITS in a row => HIGH
      - Two ENTRIES in a row => HIGH (your requested policy)

    Overlapping trips:
      - If TravelIntervals overlap => HIGH

    Long absence scrutiny:
      - 90–179 days => MEDIUM
      - 180+ days => HIGH

    Last-entry legal completeness (HIGH) when inferred_in_us=True:
      - inspected is False OR missing => HIGH
      - missing class of admission (status_or_class) => HIGH
      - missing i94_number => HIGH

    Travel vs Employment (clarification, no accusation):
      - Travel interval overlaps active employed/self_employed period
        => MEDIUM, or HIGH if travel is long (>=90 days)
    """
    if not travel_entries:
        return TravelAnalysisResult(
            intervals=[],
            issues=[],
            last_event_type=None,
            last_event_date=None,
            inferred_in_us=None,
        )

    # Filter to window and sort.
    # Tie-break: exits before entries on same day (conservative pairing).
    events = [e for e in travel_entries if window_start <= e.date <= window_end]
    events.sort(key=lambda e: (e.date, 0 if e.event_type == "exit" else 1))

    if not events:
        return TravelAnalysisResult(
            intervals=[],
            issues=[],
            last_event_type=None,
            last_event_date=None,
            inferred_in_us=None,
        )

    issues: List[Issue] = []
    intervals: List[TravelInterval] = []

    last_event = events[-1]
    if last_event.event_type == "entry":
        inferred_in_us: Optional[bool] = True
    elif last_event.event_type == "exit":
        inferred_in_us = False
    else:
        inferred_in_us = None

    last_exit: Optional[TravelEntry] = None
    last_event_seen: Optional[TravelEntry] = None

    for idx, e in enumerate(events):
        # Detect consecutive identical event types (integrity / missing opposite event).
        if last_event_seen and last_event_seen.event_type == e.event_type:
            if e.event_type == "exit":
                issues.append(
                    Issue(
                        severity="high",
                        category="travel",
                        message=f"Two exits in a row without an entry in between ({last_event_seen.date} and {e.date}).",
                        suggested_question="Please provide the re-entry date after the first exit (or confirm/correct the travel sequence).",
                    )
                )
            else:  # entry
                # Your policy: always HIGH (conservative; likely RFE-triggering inconsistency)
                issues.append(
                    Issue(
                        severity="high",
                        category="travel",
                        message=f"Two entries in a row without an exit in between ({last_event_seen.date} and {e.date}).",
                        suggested_question="Please provide the departure/exit date between these entries (or confirm/correct the travel sequence).",
                    )
                )

        if e.event_type == "exit":
            # If we already have an unmatched exit, flag (also covered by exit->exit check above, but keep explicit).
            if last_exit is not None:
                issues.append(
                    Issue(
                        severity="high",
                        category="travel",
                        message=f"Multiple exits recorded without an entry in between (previous exit on {last_exit.date}).",
                        suggested_question="Please provide the re-entry date after that exit (or confirm/correct the sequence).",
                    )
                )
            last_exit = e
            last_event_seen = e
            continue

        # ENTRY
        if last_exit is None:
            if idx == 0:
                # Baseline: exit may have occurred before window_start.
                issues.append(
                    Issue(
                        severity="low",
                        category="travel",
                        message=f"First in-window travel event is an entry on {e.date} without a preceding in-window exit.",
                        suggested_question="If you departed the U.S. before this entry outside the required window, you can ignore. Otherwise, please provide the exit date.",
                    )
                )
            else:
                # Mid-window entry without exit is a completeness/integrity issue.
                issues.append(
                    Issue(
                        severity="high",
                        category="travel",
                        message=f"Entry recorded on {e.date} without a preceding exit in the selected window.",
                        suggested_question="Please provide the exit date prior to this entry (or correct the travel sequence).",
                    )
                )
            last_event_seen = e
            continue

        # Pair exit -> entry
        days_abroad = _days_inclusive(last_exit.date, e.date)
        is_brief = days_abroad == 1

        intervals.append(
            TravelInterval(
                exit_date=last_exit.date,
                entry_date=e.date,
                days_abroad=days_abroad,
                is_brief=is_brief,
            )
        )

        # Long absence scrutiny (skip brief same-day trips)
        if not is_brief:
            if days_abroad >= 180:
                issues.append(
                    Issue(
                        severity="high",
                        category="travel",
                        message=f"Extended time outside the U.S.: {days_abroad} day(s) from {last_exit.date} to {e.date}.",
                        suggested_question="Please confirm this trip duration and explain how you maintained your U.S. residence during this period.",
                    )
                )
            elif days_abroad >= 90:
                issues.append(
                    Issue(
                        severity="medium",
                        category="travel",
                        message=f"Significant time outside the U.S.: {days_abroad} day(s) from {last_exit.date} to {e.date}.",
                        suggested_question="Please confirm this trip duration and whether it affected your U.S. residence or employment.",
                    )
                )

        last_exit = None
        last_event_seen = e

    # Unmatched exit at end => HIGH
    if last_exit is not None:
        issues.append(
            Issue(
                severity="high",
                category="travel",
                message=f"Exit recorded on {last_exit.date} without a corresponding entry date in the selected window.",
                suggested_question="Please provide your re-entry date after this exit (or confirm you have not re-entered yet).",
            )
        )

    # Overlapping travel intervals => HIGH (sweep)
    if len(intervals) >= 2:
        sorted_intervals = sorted(intervals, key=lambda x: (x.exit_date, x.entry_date))
        active = sorted_intervals[0]
        for curr in sorted_intervals[1:]:
            if _ranges_overlap(active.exit_date, active.entry_date, curr.exit_date, curr.entry_date):
                issues.append(
                    Issue(
                        severity="high",
                        category="travel",
                        message=(
                            "Overlapping travel intervals detected: "
                            f"{active.exit_date}–{active.entry_date} overlaps {curr.exit_date}–{curr.entry_date}."
                        ),
                        suggested_question="Please correct the travel dates so trips do not overlap.",
                    )
                )
            # advance active to the interval with the later entry_date
            if curr.entry_date > active.entry_date:
                active = curr

    # Last Entry Legal Status checks (HIGH) when inferred_in_us=True
    last_entry: Optional[TravelEntry] = None
    for e in reversed(events):
        if e.event_type == "entry":
            last_entry = e
            break

    if inferred_in_us is True and last_entry is not None:
        if last_entry.inspected is False:
            issues.append(
                Issue(
                    severity="high",
                    category="travel",
                    message=f"Last entry on {last_entry.date} indicates NOT inspected/admitted/paroled.",
                    suggested_question="Please confirm how you entered the U.S. on that date. Adjustment of Status generally requires inspection/admission or parole.",
                )
            )
        if last_entry.inspected is None:
            issues.append(
                Issue(
                    severity="high",
                    category="travel",
                    message=f"Last entry on {last_entry.date} is missing whether you were inspected/admitted/paroled.",
                    suggested_question="Were you inspected/admitted/paroled on your last entry? If yes, provide class of admission and I-94 number (if issued).",
                )
            )
        if not last_entry.status_or_class:
            issues.append(
                Issue(
                    severity="high",
                    category="travel",
                    message=f"Last entry on {last_entry.date} is missing class of admission/status.",
                    suggested_question="Please provide the class of admission for your last entry (e.g., B2, F1, H1B, parole).",
                )
            )
        if not last_entry.i94_number:
            issues.append(
                Issue(
                    severity="high",
                    category="travel",
                    message=f"Last entry on {last_entry.date} is missing I-94 number.",
                    suggested_question="Please provide the I-94 number for your last entry (electronic or paper). If no new I-94 was issued for a brief trip, please confirm.",
                )
            )

    # Travel vs Employment overlap (clarification, not accusation)
    if employment:
        emp_ranges = _build_employment_ranges(employment, window_start=window_start, window_end=window_end)

        for t in intervals:
            if t.is_brief:
                continue  # don't over-flag same-day border runs

            for emp_start, emp_end, emp in emp_ranges:
                if emp.employment_type not in {"employed", "self_employed"}:
                    continue

                if _ranges_overlap(t.exit_date, t.entry_date, emp_start, emp_end):
                    sev: Literal["high", "medium"] = "high" if t.days_abroad >= 90 else "medium"
                    issues.append(
                        Issue(
                            severity=sev,
                            category="travel",
                            message=(
                                f"Travel interval {t.exit_date}–{t.entry_date} overlaps an active "
                                f"{emp.employment_type} period ({emp_start}–{emp_end}) at {emp.employer!r}."
                            ),
                            suggested_question=(
                                "Please confirm whether you were working remotely while abroad, on leave, or if the employment dates should be adjusted. "
                                "If applicable, clarify your work location during the trip."
                            ),
                        )
                    )

    return TravelAnalysisResult(
        intervals=intervals,
        issues=issues,
        last_event_type=last_event.event_type,
        last_event_date=last_event.date,
        inferred_in_us=inferred_in_us,
    )
