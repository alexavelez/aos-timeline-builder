# src/validate.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, List, Literal

from src.models import AddressEntry  # adjust to ".models" if you prefer package imports


DatePrecision = Literal["day", "month", "year"]


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


def _last_day_of_month(y: int, m: int) -> date:
    if m == 12:
        return date(y, 12, 31)
    return date(y, m + 1, 1) - timedelta(days=1)


def _precision_range_start(dwp: DateWithPrecision) -> date:
    """
    Earliest possible date covered by this value given its precision.
    """
    if dwp.precision == "day":
        return dwp.value
    if dwp.precision == "month":
        return date(dwp.value.year, dwp.value.month, 1)
    # year
    return date(dwp.value.year, 1, 1)


def _precision_range_end(dwp: DateWithPrecision) -> date:
    """
    Latest possible date covered by this value given its precision.
    """
    if dwp.precision == "day":
        return dwp.value
    if dwp.precision == "month":
        return _last_day_of_month(dwp.value.year, dwp.value.month)
    # year
    return date(dwp.value.year, 12, 31)


def detect_address_gaps(
    addresses: List[AddressEntry],
    *,
    window_start: date,
    window_end: date,
) -> List[Issue]:
    """
    Precision-aware gap detection for residential address history.

    Each entry is treated as a COVERAGE RANGE:
      start = earliest possible start based on from_precision
      end   = latest possible end based on to_precision
    date_to=None is treated as "Present" -> window_end.
    """
    issues: List[Issue] = []

    if not addresses:
        return [
            Issue(
                severity="high",
                category="address_history",
                message="No residential addresses provided for the selected window.",
                suggested_question="Please provide your residential address history for the required period.",
            )
        ]

    # Build coverage ranges: (start, end, entry)
    ranges = []
    for entry in addresses:
        # Start coverage
        start_dwp = DateWithPrecision(entry.date_from, entry.from_precision)
        start = _precision_range_start(start_dwp)

        # End coverage (Present -> window_end)
        effective_end_date = entry.date_to or window_end
        end_precision = entry.to_precision if entry.date_to is not None else "day"
        # ^ If date_to is None ("Present"), treat as exact day at window_end
        end_dwp = DateWithPrecision(effective_end_date, end_precision)
        end = _precision_range_end(end_dwp)

        # Clamp to the window
        if end < window_start or start > window_end:
            continue
        start = max(start, window_start)
        end = min(end, window_end)

        ranges.append((start, end, entry))

    if not ranges:
        return [
            Issue(
                severity="high",
                category="address_history",
                message="No residential addresses overlap the required window.",
                suggested_question="Please confirm your residential address history for the required period.",
            )
        ]

    # Sort by start then end
    ranges.sort(key=lambda x: (x[0], x[1]))

    # Gap at beginning
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

    # Walk and find gaps
    prev_start, prev_end, _prev_entry = ranges[0]
    for curr_start, curr_end, _curr_entry in ranges[1:]:
        if prev_end + timedelta(days=1) < curr_start:
            gap_from = prev_end + timedelta(days=1)
            gap_to = curr_start - timedelta(days=1)
            gap_days = (gap_to - gap_from).days + 1

            issues.append(
                Issue(
                    severity="high",
                    category="address_history",
                    message=f"Unexplained address gap of {gap_days} day(s): {gap_from} to {gap_to}.",
                    suggested_question=f"Where did you live from {gap_from} to {gap_to}?",
                )
            )

        # extend coverage through overlaps/back-to-back
        prev_end = max(prev_end, curr_end)

    # Gap at end
    if prev_end < window_end:
        gap_from = prev_end + timedelta(days=1)
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
