# src/glue.py

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple, Literal
from .issues import tag_issues

from .models import (
    AddressEntry,
    PostalAddress,
    AddressType,
    DatePrecision,
    EmploymentEntry,
    EmploymentType,
    TravelEntry,
    TravelEventType,
)
from .normalize import normalize_date, NormalizedDate
from .validate import Issue


# ======================================================
# Raw snapshot (attorney packet safety net)
# ======================================================

@dataclass(frozen=True)
class RawSnapshot:
    """
    A small record you can include in the attorney packet to show what the user actually typed.
    """
    id: str  # e.g., "addr_0", "emp_2", "trv_1"
    section: Literal["address", "employment", "travel", "person", "case"]
    raw: Dict[str, Any]
    notes: Optional[str] = None


# ======================================================
# Country/state helpers (gentle USCIS-aligned warnings)
# ======================================================

def _is_us_country(country: str) -> bool:
    c = country.strip().lower()
    return c in {"us", "usa", "united states", "united states of america"}


def _looks_like_state_code(state: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]{2}", state.strip()))


# ======================================================
# Date helpers
# ======================================================

def _fmt_allowed_formats_with_present() -> str:
    return "YYYY-MM-DD, YYYY/MM/DD, MM/DD/YYYY, YYYY-MM, YYYY/MM, MM/YYYY, MM-YYYY, YYYY, or 'Present'"


def _fmt_allowed_formats_no_present() -> str:
    return "YYYY-MM-DD, YYYY/MM/DD, MM/DD/YYYY, YYYY-MM, YYYY/MM, MM/YYYY, MM-YYYY, or YYYY"



def require_date(
    *,
    field_label: str,
    raw_text: Optional[str],
    assume_us_mdy: bool = True,
    allow_present: bool = True,
    issues_category: str = "date",
) -> Tuple[Optional[date], DatePrecision, bool, List[Issue]]:
    """
    Parse a date string using normalize_date(). Always returns issues if unknown/invalid.
    Never raises.

    Returns:
      (value, precision, is_present, issues)

    Rules:
      - Unknown/invalid -> value=None, precision="unknown", Issue created
      - Present -> is_present=True (allowed only if allow_present=True)
    """
    nd: NormalizedDate = normalize_date(raw_text, assume_us_mdy=assume_us_mdy)
    issues: List[Issue] = []

    if nd.is_present:
        if not allow_present:
            issues.append(
                Issue(
                    severity="high",
                    category=issues_category,
                    message=f"{field_label}: 'Present' is not allowed here.",
                    suggested_question=(f"Please provide an actual date for {field_label} " 
                                        f"({_fmt_allowed_formats_no_present()})."
                    ),

                )
            )
            return None, "unknown", False, issues

        # Caller decides how to represent Present; for models we typically store date_to=None
        return None, "day", True, issues

    if nd.precision == "unknown" or nd.value is None:
        raw_display = raw_text if raw_text is not None and raw_text.strip() else "(blank)"
        issues.append(
            Issue(
                severity="high",
                category=issues_category,
                message=f"Invalid or unrecognized date for {field_label}: {raw_display!r}.",
                suggested_question=(f"Please provide a valid date for {field_label} in one of: "
                                    f"{_fmt_allowed_formats_with_present() if allow_present else _fmt_allowed_formats_no_present()}."
                ),

            )
        )
        return None, "unknown", False, issues

    # nd.precision is day/month/year here and nd.value is not None
    return nd.value, nd.precision, False, issues


def _require_str(
    *,
    field_label: str,
    raw_value: Optional[str],
    issues_category: str,
    severity: Literal["high", "medium", "low"] = "high",
) -> Tuple[Optional[str], List[Issue]]:
    issues: List[Issue] = []
    if raw_value is None or not str(raw_value).strip():
        issues.append(
            Issue(
                severity=severity,
                category=issues_category,
                message=f"Missing required field: {field_label}.",
                suggested_question=f"Please provide {field_label}.",
            )
        )
        return None, issues
    return str(raw_value).strip(), issues


# ======================================================
# Address glue
# ======================================================

def parse_postal_address(
    raw: Dict[str, Any],
    *,
    issues_category: str = "address_history",
) -> Tuple[Optional[PostalAddress], List[Issue]]:
    """
    Minimal, strict-ish PostalAddress builder from a raw dict.

    Required keys (MVP):
      street_name, city, country
    Optional:
      unit_type, unit_number, state_province, zip_code

    Adds a gentle USCIS-aligned warning:
      If country is USA/US/United States -> warn (medium) when state_province isn't a 2-letter code.
    """
    issues: List[Issue] = []

    street, iss = _require_str(field_label="street_name", raw_value=raw.get("street_name"), issues_category=issues_category)
    issues.extend(iss)
    city, iss = _require_str(field_label="city", raw_value=raw.get("city"), issues_category=issues_category)
    issues.extend(iss)
    country, iss = _require_str(field_label="country", raw_value=raw.get("country"), issues_category=issues_category)
    issues.extend(iss)

    # If core fields missing, return None + issues (do not crash)
    if issues:
        return None, issues

    # Gentle warning: US state code format (do NOT hard-fail)
    state_raw = raw.get("state_province")
    if isinstance(state_raw, str) and state_raw.strip():
        if _is_us_country(country) and not _looks_like_state_code(state_raw):
            issues.append(
                Issue(
                    severity="medium",
                    category=issues_category,
                    message=f"For U.S. addresses, USCIS prefers 2-letter state codes. You entered {state_raw!r}.",
                    suggested_question="Please confirm the state as a 2-letter code (e.g., NC, NY).",
                )
            )

    try:
        addr = PostalAddress(
            street_name=street,
            unit_type=raw.get("unit_type"),
            unit_number=raw.get("unit_number"),
            city=city,
            state_province=raw.get("state_province"),
            zip_code=raw.get("zip_code"),
            country=country,
        )
        return addr, issues
    except Exception as e:
        issues.append(
            Issue(
                severity="high",
                category=issues_category,
                message=f"Address could not be parsed due to validation error: {e}",
                suggested_question="Please confirm the address fields (street, unit, city, state, zip, country).",
            )
        )
        return None, issues


def parse_address_entry(
    raw: Dict[str, Any],
    *,
    ref_id: str,
    assume_us_mdy: bool = True,
) -> Tuple[Optional[AddressEntry], List[Issue], RawSnapshot]:
    """
    Build one AddressEntry from a raw dict input.
    Critical rule: if required fields (like start date) are invalid/unknown, we DO NOT silently omit it.
    We return issues + a raw snapshot so it can be reviewed.

    Accepts either nested {"address": {...}} or a flat dictionary.
    """
    issues: List[Issue] = []
    snapshot = RawSnapshot(id=ref_id, section="address", raw=raw)

    # Accept either nested {"address": {...}} or flat dict
    addr_raw = raw.get("address") if isinstance(raw.get("address"), dict) else raw
    addr, addr_issues = parse_postal_address(addr_raw, issues_category="address_history")
    issues.extend(addr_issues)

    date_from_value, from_prec, _from_present, iss = require_date(
        field_label="address start date (date_from)",
        raw_text=raw.get("date_from"),
        assume_us_mdy=assume_us_mdy,
        allow_present=False,
        issues_category="address_history",
    )
    issues.extend(iss)

    date_to_raw = raw.get("date_to")
    date_to_value, to_prec, to_present, iss = require_date(
        field_label="address end date (date_to)",
        raw_text=date_to_raw,
        assume_us_mdy=assume_us_mdy,
        allow_present=True,
        issues_category="address_history",
    )
    issues.extend(iss)

    # If present, represent as None in the model (open-ended)
    if to_present:
        date_to_value = None  # to_prec stays "day" by our require_date rule

    # Address type (warn + default if unknown)
    raw_type = raw.get("address_type", "lived")
    if raw_type not in {"lived", "temporary", "mailing"}:
        issues.append(
            Issue(
                severity="medium",
                category="address_history",
                message=f"Unknown address_type {raw_type!r}; defaulted to 'lived'.",
                suggested_question="Please confirm whether this was a lived/temporary/mailing address.",
            )
        )
        address_type: AddressType = "lived"
    else:
        address_type = raw_type  # type: ignore

    # If core requirements missing, return None but keep issues + snapshot (no silent omit)
    if addr is None or date_from_value is None:
        issues = tag_issues(issues, ref_id)
        return None, issues, snapshot

    try:
        entry = AddressEntry(
            address=addr,
            date_from=date_from_value,
            from_precision=from_prec if from_prec in ("day", "month", "year") else "day",
            date_to=date_to_value,
            to_precision=to_prec if to_prec in ("day", "month", "year") else "day",
            address_type=address_type,
            notes=raw.get("notes"),
        )
        issues = tag_issues(issues, ref_id)
        return entry, issues, snapshot
    except Exception as e:
        issues.append(
            Issue(
                severity="high",
                category="address_history",
                message=f"Address entry could not be built due to validation error: {e}",
                suggested_question="Please confirm the address entry fields and dates.",
            )
        )
        issues = tag_issues(issues, ref_id)
        return None, issues, snapshot


def parse_address_list(
    raw_list: List[Dict[str, Any]],
    *,
    assume_us_mdy: bool = True,
    id_prefix: str = "addr",
) -> Tuple[List[AddressEntry], List[Issue], List[RawSnapshot]]:
    """
    Parse a list of raw address dicts into AddressEntry objects.
    Never silently drops errors: invalid entries yield issues + snapshots with IDs.
    """
    entries: List[AddressEntry] = []
    issues: List[Issue] = []
    snapshots: List[RawSnapshot] = []

    for idx, raw in enumerate(raw_list):
        ref_id = f"{id_prefix}_{idx}"
        entry, entry_issues, snap = parse_address_entry(raw, ref_id=ref_id, assume_us_mdy=assume_us_mdy)
        snapshots.append(snap)
        issues.extend(entry_issues)
        if entry is not None:
            entries.append(entry)

    return entries, issues, snapshots


# ======================================================
# Employment glue
# ======================================================

def parse_employment_entry(
    raw: Dict[str, Any],
    *,
    ref_id: str,
    assume_us_mdy: bool = True,
) -> Tuple[Optional[EmploymentEntry], List[Issue], RawSnapshot]:
    issues: List[Issue] = []
    snapshot = RawSnapshot(id=ref_id, section="employment", raw=raw)

    employer, iss = _require_str(field_label="employer", raw_value=raw.get("employer"), issues_category="employment")
    issues.extend(iss)

    date_from_value, from_prec, _from_present, iss = require_date(
        field_label="employment start date (date_from)",
        raw_text=raw.get("date_from"),
        assume_us_mdy=assume_us_mdy,
        allow_present=False,
        issues_category="employment",
    )
    issues.extend(iss)

    date_to_value, to_prec, to_present, iss = require_date(
        field_label="employment end date (date_to)",
        raw_text=raw.get("date_to"),
        assume_us_mdy=assume_us_mdy,
        allow_present=True,
        issues_category="employment",
    )
    issues.extend(iss)

    if to_present:
        date_to_value = None


    raw_type = raw.get("employment_type")
    if raw_type not in {"employed", "self_employed", "unemployed"}:
        issues.append(
            Issue(
                severity="medium",
                category="employment",
                message=f"Unknown employment_type {raw_type!r}; defaulted to 'employed'.",
                suggested_question="Please confirm employment type: employed, self_employed, or unemployed.",
            )
        )
        employment_type: EmploymentType = "employed"
    else:
        employment_type = raw_type  # type: ignore

    employer_address = None
    if isinstance(raw.get("employer_address"), dict):
        employer_address, addr_issues = parse_postal_address(raw["employer_address"], issues_category="employment")
        issues.extend(addr_issues)

    if employer is None or date_from_value is None:
        issues = tag_issues(issues, ref_id)
        return None, issues, snapshot

    try:
        entry = EmploymentEntry(
            employer=employer,
            role=raw.get("role"),
            employer_address=employer_address,
            date_from=date_from_value,
            from_precision=from_prec if from_prec in ("day", "month", "year") else "day",
            date_to=date_to_value,
            to_precision=to_prec if to_prec in ("day", "month", "year") else "day",
            employment_type=employment_type,
            notes=raw.get("notes"),
        )
        issues = tag_issues(issues, ref_id)
        return entry, issues, snapshot
    except Exception as e:
        issues.append(
            Issue(
                severity="high",
                category="employment",
                message=f"Employment entry could not be built due to validation error: {e}",
                suggested_question="Please confirm employer, dates, and employment type.",
            )
        )
        issues = tag_issues(issues, ref_id)
        return None, issues, snapshot


def parse_employment_list(
    raw_list: List[Dict[str, Any]],
    *,
    assume_us_mdy: bool = True,
    id_prefix: str = "emp",
) -> Tuple[List[EmploymentEntry], List[Issue], List[RawSnapshot]]:
    entries: List[EmploymentEntry] = []
    issues: List[Issue] = []
    snapshots: List[RawSnapshot] = []

    for idx, raw in enumerate(raw_list):
        ref_id = f"{id_prefix}_{idx}"
        entry, entry_issues, snap = parse_employment_entry(raw, ref_id=ref_id, assume_us_mdy=assume_us_mdy)
        snapshots.append(snap)
        issues.extend(entry_issues)
        if entry is not None:
            entries.append(entry)

    return entries, issues, snapshots


# ======================================================
# Travel glue
# ======================================================

def parse_travel_entry(
    raw: Dict[str, Any],
    *,
    ref_id: str,
    assume_us_mdy: bool = True,
) -> Tuple[Optional[TravelEntry], List[Issue], RawSnapshot]:
    issues: List[Issue] = []
    snapshot = RawSnapshot(id=ref_id, section="travel", raw=raw)

    raw_event_type = raw.get("event_type")
    if raw_event_type not in {"entry", "exit"}:
        issues.append(
            Issue(
                severity="high",
                category="travel",
                message=f"Missing/invalid travel event_type {raw_event_type!r}.",
                suggested_question="Please specify travel event type: entry or exit.",
            )
        )
        event_type: Optional[TravelEventType] = None
    else:
        event_type = raw_event_type  # type: ignore

    dt_value, _prec, _is_present, iss = require_date(
        field_label="travel event date",
        raw_text=raw.get("date"),
        assume_us_mdy=assume_us_mdy,
        allow_present=False,  # Present is not valid for a discrete travel event
        issues_category="travel",
    )
    issues.extend(iss)

    if event_type is None or dt_value is None:
        issues = tag_issues(issues, ref_id)
        return None, issues, snapshot

    try:
        entry = TravelEntry(
            event_type=event_type,
            date=dt_value,
            port_or_city=raw.get("port_or_city"),
            status_or_class=raw.get("status_or_class"),
            i94_number=raw.get("i94_number"),      
            inspected=raw.get("inspected"),        
            notes=raw.get("notes"),
        )
        
        issues = tag_issues(issues, ref_id)
        return entry, issues, snapshot
    except Exception as e:
        issues.append(
            Issue(
                severity="high",
                category="travel",
                message=f"Travel entry could not be built due to validation error: {e}",
                suggested_question="Please confirm travel date and event fields.",
            )
        )
        issues = tag_issues(issues, ref_id)
        return None, issues, snapshot


def parse_travel_list(
    raw_list: List[Dict[str, Any]],
    *,
    assume_us_mdy: bool = True,
    id_prefix: str = "trv",
) -> Tuple[List[TravelEntry], List[Issue], List[RawSnapshot]]:
    entries: List[TravelEntry] = []
    issues: List[Issue] = []
    snapshots: List[RawSnapshot] = []

    for idx, raw in enumerate(raw_list):
        ref_id = f"{id_prefix}_{idx}"
        entry, entry_issues, snap = parse_travel_entry(raw, ref_id=ref_id, assume_us_mdy=assume_us_mdy)
        snapshots.append(snap)
        issues.extend(entry_issues)
        if entry is not None:
            entries.append(entry)

    return entries, issues, snapshots
