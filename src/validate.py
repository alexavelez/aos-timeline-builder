# src/validate.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, List, Literal

from .models import AddressEntry, DatePrecision


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


def detect_address_gaps(
    addresses: List[AddressEntry],
    *,
    window_start: date,
    window_end: date,
) -> List[Issue]:
    """
    Precision-aware gap detection for residential address history.

    Each AddressEntry covers a RANGE:
      start = earliest possible date based on from_precision
      end   = latest possible date based on to_precision

    date_to=None means "Present", which we treat as covering through window_end.
    A gap exists if:
      prev_end + 1 day < next_start
    """
    if not addresses:
        return [
            Issue(
                severity="high",
                category="address_history",
                message="No residential addresses provided for the selected window.",
                suggested_question="Please provide your residential address history for the required period.",
            )
        ]

    ranges = []
    for entry in addresses:
        start = _precision_range_start(DateWithPrecision(entry.date_from, entry.from_precision))

        effective_end = entry.date_to or window_end
        # If date_to is None ("Present"), treat it as day-precision at window_end
        end_precision: DatePrecision = entry.to_precision if entry.date_to is not None else "day"
        end = _precision_range_end(DateWithPrecision(effective_end, end_precision))

        # Ignore entries fully outside window
        if end < window_start or start > window_end:
            continue

        # Clamp to window
        start = max(start, window_start)
        end = min(end, window_end)

        ranges.append((start, end))

    if not ranges:
        return [
            Issue(
                severity="high",
                category="address_history",
                message="No residential addresses overlap the required window.",
                suggested_question="Please confirm your residential address history for the required period.",
            )
        ]

    ranges.sort(key=lambda x: (x[0], x[1]))

    issues: List[Issue] = []

    # Start gap
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

    # Middle gaps
    prev_end = ranges[0][1]
    for curr_start, curr_end in ranges[1:]:
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

        prev_end = max(prev_end, curr_end)

    # End gap
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
