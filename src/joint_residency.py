# src/joint_residency.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Literal, Tuple

from .models import AddressEntry, ImmigrationCase, DatePrecision
from .validate import Issue
from .canonicalize import address_keys


MatchType = Literal["strict", "loose"]


@dataclass(frozen=True)
class AddressRange:
    start: date
    end: date
    entry: AddressEntry
    strict_key: str
    loose_key: str


@dataclass(frozen=True)
class SharedResidenceWindow:
    start: date
    end: date
    match_type: MatchType
    petitioner_entry: AddressEntry
    beneficiary_entry: AddressEntry


@dataclass(frozen=True)
class JointResidencyResult:
    first_shared_date: Optional[date]
    match_type: Optional[MatchType]
    windows: List[SharedResidenceWindow]
    issues: List[Issue]


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


def _build_ranges(
    addresses: List[AddressEntry],
    *,
    window_start: date,
    window_end: date,
) -> List[AddressRange]:
    ranges: List[AddressRange] = []

    for entry in addresses:
        start = _precision_range_start(entry.date_from, entry.from_precision)

        effective_end = entry.date_to or window_end
        end_precision: DatePrecision = entry.to_precision if entry.date_to is not None else "day"
        end = _precision_range_end(effective_end, end_precision)

        # ignore outside window
        if end < window_start or start > window_end:
            continue

        # clamp to window
        start = max(start, window_start)
        end = min(end, window_end)

        keys = address_keys(entry.address)
        ranges.append(
            AddressRange(
                start=start,
                end=end,
                entry=entry,
                strict_key=keys.strict_key,
                loose_key=keys.loose_key,
            )
        )

    ranges.sort(key=lambda r: (r.start, r.end))
    return ranges


def _overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> Optional[Tuple[date, date]]:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if start <= end:
        return start, end
    return None


def detect_joint_residency_start(
    case: ImmigrationCase,
    *,
    window_start: date,
    window_end: date,
) -> JointResidencyResult:
    """
    Find earliest shared residential window between petitioner and beneficiary.

    Matching strategy:
      1) STRICT match (unit + ZIP5 + normalized state/country, etc.)
      2) LOOSE match (street + city + state + country; ignores unit + zip)

    Output:
      - first_shared_date: earliest date where a shared residence overlap exists
      - match_type: "strict" if earliest is strict, otherwise "loose"
      - windows: all shared overlap windows (strict and loose)
      - issues:
          * if only loose matches exist -> medium (near-match; unit/zip differences)
          * if no shared window exists -> medium (living arrangement clarification)
    """
    pet_ranges = _build_ranges(case.petitioner.addresses_lived, window_start=window_start, window_end=window_end)
    ben_ranges = _build_ranges(case.beneficiary.addresses_lived, window_start=window_start, window_end=window_end)

    windows: List[SharedResidenceWindow] = []

    # Brute force is OK for small lists (typical USCIS timelines). Optimize later if needed.
    for pr in pet_ranges:
        for br in ben_ranges:
            ov = _overlap(pr.start, pr.end, br.start, br.end)
            if not ov:
                continue

            # strict match first
            if pr.strict_key == br.strict_key:
                windows.append(
                    SharedResidenceWindow(
                        start=ov[0],
                        end=ov[1],
                        match_type="strict",
                        petitioner_entry=pr.entry,
                        beneficiary_entry=br.entry,
                    )
                )
                continue

            # loose match as fallback
            if pr.loose_key == br.loose_key:
                windows.append(
                    SharedResidenceWindow(
                        start=ov[0],
                        end=ov[1],
                        match_type="loose",
                        petitioner_entry=pr.entry,
                        beneficiary_entry=br.entry,
                    )
                )

    if not windows:
        issues = [
            Issue(
                severity="medium",
                category="joint_residency",
                ref_id="joint_residency",
                message="No shared residential address overlap was detected between petitioner and beneficiary in the selected window.",
                suggested_question=(
                    f"Have you and your spouse lived together at any point between {window_start} and {window_end}? "
                    "If yes, please provide the shared address and dates. If not, briefly explain your living arrangement."
                ),
            )
        ]
        return JointResidencyResult(
            first_shared_date=None,
            match_type=None,
            windows=[],
            issues=issues,
        )

    # Sort windows by start date, prefer strict when starts are equal
    priority = {"strict": 0, "loose": 1}
    windows.sort(key=lambda w: (w.start, priority[w.match_type], w.end))

    first = windows[0]

    issues: List[Issue] = []

    # If we have NO strict windows at all, only loose matches exist -> near-match concern
    has_strict = any(w.match_type == "strict" for w in windows)
    if not has_strict:
        issues.append(
            Issue(
                severity="medium",
                category="joint_residency",
                ref_id="joint_residency",
                message=(
                    "A possible shared residence was detected, but only via loose address matching "
                    "(unit/ZIP differences may exist)."
                ),
                suggested_question=(
                    "Please confirm your shared residence address details (unit/apartment and ZIP). "
                    "If you lived together, which exact address should be used on the forms?"
                ),
            )
        )

    return JointResidencyResult(
        first_shared_date=first.start,
        match_type=first.match_type,
        windows=windows,
        issues=issues,
    )
