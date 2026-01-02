# src/validate.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, List, Literal, Tuple

from .models import AddressEntry, EmploymentEntry, DatePrecision


@dataclass(frozen=True)
class DateWithPrecision:
    value: date
    precision: DatePrecision


@dataclass(frozen=True)
class Issue:
    severity: Literal["high", "medium", "low"]
    category: str
    message: str
    suggested_question: Optional[str] = None
    ref_id: Optional[str] = None


def _last_day_of_month(y: int, m: int) -> date:
    if m == 12:
        return date(y, 12, 31)
    return date(y, m + 1, 1) - timedelta(days=1)


def _precision_range_start(dwp: DateWithPrecision) -> date:
    """Earliest possible date for the given precision."""
    if dwp.precision == "day":
        return dwp.value
    if dwp.precision == "month":
        return date(dwp.value.year, dwp.value.month, 1)
    # year
    return date(dwp.value.year, 1, 1)


def _precision_range_end(dwp: DateWithPrecision) -> date:
    """Latest possible date for the given precision."""
    if dwp.precision == "day":
        return dwp.value
    if dwp.precision == "month":
        return _last_day_of_month(dwp.value.year, dwp.value.month)
    # year
    return date(dwp.value.year, 12, 31)


def _build_address_ranges(
    addresses: List[AddressEntry],
    *,
    window_start: date,
    window_end: date,
) -> List[Tuple[date, date, AddressEntry]]:
    """
    Convert AddressEntry records into clamped coverage ranges within [window_start, window_end].

    Each entry covers:
      start = earliest possible date based on from_precision
      end   = latest possible date based on to_precision

    date_to=None means "Present", treated as covering through window_end with day precision.
    """
    ranges: List[Tuple[date, date, AddressEntry]] = []

    for entry in addresses:
        start = _precision_range_start(DateWithPrecision(entry.date_from, entry.from_precision))

        effective_end = entry.date_to or window_end
        end_precision: DatePrecision = entry.to_precision if entry.date_to is not None else "day"
        end = _precision_range_end(DateWithPrecision(effective_end, end_precision))

        # Ignore entries fully outside window
        if end < window_start or start > window_end:
            continue

        # Clamp to window
        start = max(start, window_start)
        end = min(end, window_end)

        ranges.append((start, end, entry))

    ranges.sort(key=lambda x: (x[0], x[1]))
    return ranges


def detect_address_gaps(
    addresses: List[AddressEntry],
    *,
    window_start: date,
    window_end: date,
) -> List[Issue]:
    """
    Precision-aware gap detection for residential address history.

    Hybrid severity policy:
      - Start-of-window gaps: HIGH (even 1 day)
      - End-of-window gaps:   HIGH (even 1 day)
      - Middle gaps:
          * 1 day   -> MEDIUM
          * >=2 days -> HIGH
    """

    def _middle_gap_severity(gap_days: int) -> Literal["high", "medium"]:
        return "medium" if gap_days == 1 else "high"

    if not addresses:
        return [
            Issue(
                severity="high",
                category="address_history",
                message="No residential addresses provided for the selected window.",
                suggested_question="Please provide your residential address history for the required period.",
            )
        ]

    # Reuse shared range builder (precision-aware + window-clamped)
    raw_ranges = _build_address_ranges(addresses, window_start=window_start, window_end=window_end)

    if not raw_ranges:
        return [
            Issue(
                severity="high",
                category="address_history",
                message="No residential addresses overlap the required window.",
                suggested_question="Please confirm your residential address history for the required period.",
            )
        ]

    # We only need (start, end) for gap math
    ranges = [(start, end) for start, end, _entry in raw_ranges]

    issues: List[Issue] = []

    # Start gap (always HIGH)
    first_start = ranges[0][0]
    if first_start > window_start:
        gap_from = window_start
        gap_to = first_start - timedelta(days=1)
        issues.append(
            Issue(
                severity="high",
                category="address_history",
                message=f"Address gap at the start of the window: {gap_from} to {gap_to}.",
                suggested_question=f"Where did you live from {gap_from} to {gap_to}?",
            )
        )

    # Middle gaps (track high-water mark to handle nested/overlapping ranges)
    current_max_end = ranges[0][1]
    for curr_start, curr_end in ranges[1:]:
        if curr_start > current_max_end + timedelta(days=1):
            gap_from = current_max_end + timedelta(days=1)
            gap_to = curr_start - timedelta(days=1)
            gap_days = (gap_to - gap_from).days + 1

            issues.append(
                Issue(
                    severity=_middle_gap_severity(gap_days),
                    category="address_history",
                    message=f"Unexplained address gap of {gap_days} day(s): {gap_from} to {gap_to}.",
                    suggested_question=f"Where did you live from {gap_from} to {gap_to}?",
                )
            )

        current_max_end = max(current_max_end, curr_end)

    # End gap (always HIGH)
    if current_max_end < window_end:
        gap_from = current_max_end + timedelta(days=1)
        gap_to = window_end
        issues.append(
            Issue(
                severity="high",
                category="address_history",
                message=f"Address gap at the end of the window: {gap_from} to {gap_to}.",
                suggested_question=f"Where did you live from {gap_from} to {gap_to}?",
            )
        )

    return issues


def detect_address_overlaps(
    addresses: List[AddressEntry],
    *,
    window_start: date,
    window_end: date,
) -> List[Issue]:
    """
    Precision-aware overlap detection for residential address history.

    Overlap exists if:
      curr_start <= prev_end
    (i.e., two ranges claim coverage for the same day(s)).

    Severity policy (tiny improvement):
      - 1 day overlap   -> LOW
      - 2–29 days       -> MEDIUM
      - 30+ days        -> HIGH
    """

    def _overlap_severity(overlap_days: int) -> Literal["high", "medium", "low"]:
        if overlap_days == 1:
            return "low"
        if overlap_days < 30:
            return "medium"
        return "high"

    if not addresses:
        return []

    ranges = _build_address_ranges(addresses, window_start=window_start, window_end=window_end)
    if len(ranges) < 2:
        return []

    issues: List[Issue] = []

    prev_start, prev_end, prev_entry = ranges[0]

    for curr_start, curr_end, curr_entry in ranges[1:]:
        if curr_start <= prev_end:
            overlap_from = curr_start
            overlap_to = min(prev_end, curr_end)
            overlap_days = (overlap_to - overlap_from).days + 1

            issues.append(
                Issue(
                    severity=_overlap_severity(overlap_days),
                    category="address_history",
                    message=f"Overlapping residential addresses for {overlap_days} day(s): {overlap_from} to {overlap_to}.",
                    suggested_question=(
                        f"Two addresses appear to overlap from {overlap_from} to {overlap_to}. "
                        "Which address was your primary residence during this period (and were you temporarily staying elsewhere)?"
                    ),
                )
            )

        # Advance the "active" range to whichever extends further
        if curr_end > prev_end:
            prev_start, prev_end, prev_entry = curr_start, curr_end, curr_entry

    return issues


# ======================================================
# Employment validation
# ======================================================

def _build_employment_ranges(
    employment: List[EmploymentEntry],
    *,
    window_start: date,
    window_end: date,
) -> List[Tuple[date, date, EmploymentEntry]]:
    """
    Convert EmploymentEntry records into clamped coverage ranges within [window_start, window_end].

    Each entry covers:
      start = earliest possible date based on from_precision
      end   = latest possible date based on to_precision

    date_to=None means "Present", treated as covering through window_end with day precision.
    """
    ranges: List[Tuple[date, date, EmploymentEntry]] = []

    for entry in employment:
        start = _precision_range_start(DateWithPrecision(entry.date_from, entry.from_precision))

        effective_end = entry.date_to or window_end
        end_precision: DatePrecision = entry.to_precision if entry.date_to is not None else "day"
        end = _precision_range_end(DateWithPrecision(effective_end, end_precision))

        # Ignore entries fully outside window
        if end < window_start or start > window_end:
            continue

        # Clamp to window
        start = max(start, window_start)
        end = min(end, window_end)

        ranges.append((start, end, entry))

    ranges.sort(key=lambda x: (x[0], x[1]))
    return ranges


def detect_employment_gaps(
    employment: List[EmploymentEntry],
    *,
    window_start: date,
    window_end: date,
) -> List[Issue]:
    """
    Precision-aware gap detection for employment history.

    Hybrid severity policy (same as addresses):
      - Start-of-window gaps: HIGH (even 1 day)
      - End-of-window gaps:   HIGH (even 1 day)
      - Middle gaps:
          * 1 day   -> MEDIUM
          * >=2 days -> HIGH

    Notes:
      - This treats ANY employment entry as coverage, including 'unemployed',
        which is usually what USCIS wants (continuity + explanation).
    """

    def _middle_gap_severity(gap_days: int) -> Literal["high", "medium"]:
        return "medium" if gap_days == 1 else "high"

    if not employment:
        return [
            Issue(
                severity="high",
                category="employment",
                message="No employment history provided for the selected window.",
                suggested_question="Please provide your employment history (including unemployment) for the required period.",
            )
        ]

    raw_ranges = _build_employment_ranges(employment, window_start=window_start, window_end=window_end)

    if not raw_ranges:
        return [
            Issue(
                severity="high",
                category="employment",
                message="No employment entries overlap the required window.",
                suggested_question="Please confirm your employment history for the required period.",
            )
        ]

    # We only need (start, end) for gap math
    ranges = [(start, end) for start, end, _entry in raw_ranges]

    issues: List[Issue] = []

    # Start gap (always HIGH)
    first_start = ranges[0][0]
    if first_start > window_start:
        gap_from = window_start
        gap_to = first_start - timedelta(days=1)
        issues.append(
            Issue(
                severity="high",
                category="employment",
                message=f"Employment gap at the start of the window: {gap_from} to {gap_to}.",
                suggested_question=f"What was your employment status from {gap_from} to {gap_to} (employed, self-employed, unemployed)?",
            )
        )

    # Middle gaps (track high-water mark to handle nested/overlapping ranges)
    current_max_end = ranges[0][1]
    for curr_start, curr_end in ranges[1:]:
        if curr_start > current_max_end + timedelta(days=1):
            gap_from = current_max_end + timedelta(days=1)
            gap_to = curr_start - timedelta(days=1)
            gap_days = (gap_to - gap_from).days + 1

            issues.append(
                Issue(
                    severity=_middle_gap_severity(gap_days),
                    category="employment",
                    message=f"Unexplained employment gap of {gap_days} day(s): {gap_from} to {gap_to}.",
                    suggested_question=f"What was your employment status from {gap_from} to {gap_to}?",
                )
            )

        current_max_end = max(current_max_end, curr_end)

    # End gap (always HIGH)
    if current_max_end < window_end:
        gap_from = current_max_end + timedelta(days=1)
        gap_to = window_end
        issues.append(
            Issue(
                severity="high",
                category="employment",
                message=f"Employment gap at the end of the window: {gap_from} to {gap_to}.",
                suggested_question=f"What was your employment status from {gap_from} to {gap_to}?",
            )
        )

    return issues

def detect_employment_overlaps(
    employment: List[EmploymentEntry],
    *,
    window_start: date,
    window_end: date,
) -> List[Issue]:
    """
    Precision-aware overlap detection for employment history.

    Overlap exists if:
      curr_start <= prev_end

    NOTE: Overlapping jobs can be normal (two part-time jobs, switching, etc.).
    So we keep severity a bit softer than address overlaps.

    Severity policy:
      - 1 day overlap   -> LOW
      - 2–29 days       -> MEDIUM
      - 30+ days        -> HIGH
    """

    def _overlap_severity(overlap_days: int) -> Literal["high", "medium", "low"]:
        if overlap_days == 1:
            return "low"
        if overlap_days < 30:
            return "medium"
        return "high"

    if not employment:
        return []

    ranges = _build_employment_ranges(employment, window_start=window_start, window_end=window_end)
    if len(ranges) < 2:
        return []

    issues: List[Issue] = []

    prev_start, prev_end, prev_entry = ranges[0]

    for curr_start, curr_end, curr_entry in ranges[1:]:
        if curr_start <= prev_end:
            overlap_from = curr_start
            overlap_to = min(prev_end, curr_end)
            overlap_days = (overlap_to - overlap_from).days + 1

            issues.append(
                Issue(
                    severity=_overlap_severity(overlap_days),
                    category="employment",
                    message=(
                        f"Overlapping employment entries for {overlap_days} day(s): "
                        f"{overlap_from} to {overlap_to}."
                    ),
                    suggested_question=(
                        f"Two employment entries overlap from {overlap_from} to {overlap_to}. "
                        "Did you hold multiple jobs at the same time, or should one job’s end/start date be corrected?"
                    ),
                )
            )

        # Advance to whichever range extends further
        if curr_end > prev_end:
            prev_start, prev_end, prev_entry = curr_start, curr_end, curr_entry

    return issues

