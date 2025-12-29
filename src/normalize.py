# src/normalize.py

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional, Literal


DatePrecision = Literal["day", "month", "year", "unknown"]


@dataclass(frozen=True)
class NormalizedDate:
    """
    value:
      - datetime.date when known
      - None when unknown or when representing 'Present'

    precision:
      - day | month | year | unknown

    is_present:
      - True ONLY if the input explicitly meant 'Present'
    """
    value: Optional[date]
    precision: DatePrecision
    is_present: bool = False


def _safe_date(y: int, m: int, d: int) -> Optional[date]:
    """Return None instead of raising ValueError for invalid dates (e.g., 02/31/2023)."""
    try:
        return date(y, m, d)
    except ValueError:
        return None


def normalize_date(text: Optional[str], assume_us_mdy: bool = True) -> NormalizedDate:
    """
    Normalize common intake date strings into a comparable date + precision.

    Supported inputs:
      - "Present", "Current", "Now" (any capitalization)

      Day precision:
      - "YYYY-MM-DD"
      - "YYYY/MM/DD"        (added)
      - "MM/DD/YYYY"        (US-style; only when assume_us_mdy=True)

      Month precision:
      - "YYYY-MM"
      - "YYYY/MM"           (added)
      - "MM/YYYY"
      - "MM-YYYY"           (added)

      Year precision:
      - "YYYY"

    Design decisions:
      - Month-only dates use the 1st of the month as a placeholder
      - Year-only dates use Jan 1 as a placeholder
      - Precision is tracked separately (critical for gap detection)
      - Invalid dates NEVER crash the program
      - Unrecognized formats return precision="unknown"
    """
    if text is None:
        return NormalizedDate(value=None, precision="unknown", is_present=False)

    s = text.strip()
    if not s:
        return NormalizedDate(value=None, precision="unknown", is_present=False)

    s_lower = s.lower()
    if s_lower in {"present", "current", "now"}:
        # "Present" behaves like an open-ended date; caller decides what "today" is.
        return NormalizedDate(value=None, precision="day", is_present=True)

    # -----------------------------
    # Day precision formats
    # -----------------------------

    # YYYY-MM-DD
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        dt = _safe_date(y, mo, d)
        return (
            NormalizedDate(value=dt, precision="day", is_present=False)
            if dt
            else NormalizedDate(value=None, precision="unknown", is_present=False)
        )

    # YYYY/MM/DD  (added)
    m = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        dt = _safe_date(y, mo, d)
        return (
            NormalizedDate(value=dt, precision="day", is_present=False)
            if dt
            else NormalizedDate(value=None, precision="unknown", is_present=False)
        )

    # MM/DD/YYYY (US-style, because questionnaire specifies this format)
    if assume_us_mdy:
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
        if m:
            mo, d, y = map(int, m.groups())
            dt = _safe_date(y, mo, d)
            return (
                NormalizedDate(value=dt, precision="day", is_present=False)
                if dt
                else NormalizedDate(value=None, precision="unknown", is_present=False)
            )

    # -----------------------------
    # Month precision formats
    # -----------------------------

    # YYYY-MM
    m = re.fullmatch(r"(\d{4})-(\d{2})", s)
    if m:
        y, mo = map(int, m.groups())
        dt = _safe_date(y, mo, 1)
        return (
            NormalizedDate(value=dt, precision="month", is_present=False)
            if dt
            else NormalizedDate(value=None, precision="unknown", is_present=False)
        )

    # YYYY/MM  (added)
    m = re.fullmatch(r"(\d{4})/(\d{1,2})", s)
    if m:
        y, mo = map(int, m.groups())
        dt = _safe_date(y, mo, 1)
        return (
            NormalizedDate(value=dt, precision="month", is_present=False)
            if dt
            else NormalizedDate(value=None, precision="unknown", is_present=False)
        )

    # MM/YYYY
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
    if m:
        mo, y = map(int, m.groups())
        dt = _safe_date(y, mo, 1)
        return (
            NormalizedDate(value=dt, precision="month", is_present=False)
            if dt
            else NormalizedDate(value=None, precision="unknown", is_present=False)
        )

    # MM-YYYY  (added)
    m = re.fullmatch(r"(\d{1,2})-(\d{4})", s)
    if m:
        mo, y = map(int, m.groups())
        dt = _safe_date(y, mo, 1)
        return (
            NormalizedDate(value=dt, precision="month", is_present=False)
            if dt
            else NormalizedDate(value=None, precision="unknown", is_present=False)
        )

    # -----------------------------
    # Year precision format
    # -----------------------------

    # YYYY
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        y = int(m.group(1))
        dt = _safe_date(y, 1, 1)
        return (
            NormalizedDate(value=dt, precision="year", is_present=False)
            if dt
            else NormalizedDate(value=None, precision="unknown", is_present=False)
        )

    return NormalizedDate(value=None, precision="unknown", is_present=False)


def end_date_or_today(nd: NormalizedDate, today: Optional[date] = None) -> Optional[date]:
    """
    If end date is 'Present', return today's date.
    Otherwise return the parsed date (or None).
    """
    if nd.is_present:
        return today or date.today()
    return nd.value
