# src/pipeline.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from .issues import tag_issues


from .glue import (
    RawSnapshot,
    parse_address_list,
    parse_employment_list,
    parse_travel_list,
    require_date,
)
from .models import ImmigrationCase, PersonData
from .validate import (
    Issue,
    detect_address_gaps,
    detect_address_overlaps,
)


@dataclass(frozen=True)
class BuildResult:
    case: ImmigrationCase
    issues: List[Issue]
    snapshots: List[RawSnapshot]
    window_start: date
    window_end: date


def _compute_last_5_year_window(today: Optional[date] = None) -> Tuple[date, date]:
    """
    Compute a naive 'last 5 years' window.
    Uses 5*365 days for MVP simplicity (good enough for validation heuristics).
    Later: use relativedelta(years=5) for exact calendar logic.
    """
    end = today or date.today()
    start = end - timedelta(days=5 * 365)
    return start, end


def _build_person(
    raw_person: Dict[str, Any],
    *,
    prefix: str,
    assume_us_mdy: bool,
    issues: List[Issue],
    snapshots: List[RawSnapshot],
) -> PersonData:
    """
    Build a PersonData from a raw dict using glue parsers.
    We do NOT do names/identifiers here yet (MVP focuses on timelines).
    """
    # Addresses
    raw_addresses = raw_person.get("addresses", []) or []
    addr_entries, addr_issues, addr_snaps = parse_address_list(
        raw_addresses, assume_us_mdy=assume_us_mdy, id_prefix=f"{prefix}_addr"
    )
    issues.extend(addr_issues)
    snapshots.extend(addr_snaps)

    # Employment
    raw_employment = raw_person.get("employment", []) or []
    emp_entries, emp_issues, emp_snaps = parse_employment_list(
        raw_employment, assume_us_mdy=assume_us_mdy, id_prefix=f"{prefix}_emp"
    )
    issues.extend(emp_issues)
    snapshots.extend(emp_snaps)

    # Travel
    raw_travel = raw_person.get("travel", []) or []
    trv_entries, trv_issues, trv_snaps = parse_travel_list(
        raw_travel, assume_us_mdy=assume_us_mdy, id_prefix=f"{prefix}_trv"
    )
    issues.extend(trv_issues)
    snapshots.extend(trv_snaps)

    return PersonData(
        addresses_lived=addr_entries,
        employment=emp_entries,
        travel_entries=trv_entries,
    )


def load_case_from_json(
    raw: Dict[str, Any],
    *,
    assume_us_mdy: bool = True,
    today: Optional[date] = None,
    validate_petitioner: bool = False,
) -> BuildResult:
    """
    End-to-end pipeline:
      - Parse raw dict into ImmigrationCase (MVP fields)
      - Collect Issues + RawSnapshots (glue)
      - Compute window
      - Run validators (gaps/overlaps) and append Issues

    Notes:
      - MVP focuses on address/employment/travel timelines and marriage date.
      - Later we’ll add parsing for names, identifiers, current addresses, etc.
    """
    issues: List[Issue] = []
    snapshots: List[RawSnapshot] = []

    raw_pet = raw.get("petitioner", {}) or {}
    raw_ben = raw.get("beneficiary", {}) or {}

    petitioner = _build_person(
        raw_pet, prefix="pet", assume_us_mdy=assume_us_mdy, issues=issues, snapshots=snapshots
    )
    beneficiary = _build_person(
        raw_ben, prefix="ben", assume_us_mdy=assume_us_mdy, issues=issues, snapshots=snapshots
    )

    # Marriage block (optional)
    marriage = raw.get("marriage", {}) or {}
    marriage_date_value, _prec, is_present, m_issues = require_date(
        field_label="marriage date",
        raw_text=marriage.get("date"),
        assume_us_mdy=assume_us_mdy,
        allow_present=False,
        issues_category="marriage",
    )
    # Tag these issues to a pseudo ref_id for UI clarity
    issues.extend(tag_issues(m_issues, "case_marriage"))

    if is_present:
        # require_date(allow_present=False) should already issue an error, but keep safe behavior
        marriage_date_value = None

    case = ImmigrationCase(
        petitioner=petitioner,
        beneficiary=beneficiary,
        marriage_date=marriage_date_value,
        marriage_city=marriage.get("city"),
        marriage_state_province=marriage.get("state"),
        marriage_country=marriage.get("country"),
    )

    # Compute window (last 5 years, MVP)
    window_start, window_end = _compute_last_5_year_window(today=today)

    # Run validators on beneficiary by default (typical for AOS continuity questions)
    issues.extend(
        detect_address_gaps(
            case.beneficiary.addresses_lived,
            window_start=window_start,
            window_end=window_end,
        )
    )
    issues.extend(
        detect_address_overlaps(
            case.beneficiary.addresses_lived,
            window_start=window_start,
            window_end=window_end,
        )
    )

    # Optional: validate petitioner too
    if validate_petitioner:
        issues.extend(
            detect_address_gaps(
                case.petitioner.addresses_lived,
                window_start=window_start,
                window_end=window_end,
            )
        )
        issues.extend(
            detect_address_overlaps(
                case.petitioner.addresses_lived,
                window_start=window_start,
                window_end=window_end,
            )
        )

    return BuildResult(
        case=case,
        issues=issues,
        snapshots=snapshots,
        window_start=window_start,
        window_end=window_end,
    )
