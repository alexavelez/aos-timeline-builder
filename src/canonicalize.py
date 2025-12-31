# src/canonicalize.py

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

from .models import PostalAddress


_US_COUNTRY_ALIASES = {
    "us",
    "usa",
    "united states",
    "united states of america",
}

# Normalize common synonyms to a canonical token
_UNIT_TYPE_SYNONYMS = {
    "apt": "apt",
    "apartment": "apt",
    "unit": "unit",
    "ste": "ste",
    "suite": "ste",
    "fl": "fl",
    "floor": "fl",
}

_US_STATE_NAME_TO_CODE = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}


def _collapse_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _strip_punct_keep_alnum_space(s: str) -> str:
    # Keep letters/digits/spaces; drop punctuation like . , # etc.
    return re.sub(r"[^a-z0-9\s]", " ", s)


def normalize_text(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    t = _collapse_whitespace(s.strip().lower())
    if not t:
        return None
    t = _strip_punct_keep_alnum_space(t)
    t = _collapse_whitespace(t)
    return t or None


def normalize_country(country: Optional[str]) -> Optional[str]:
    c = normalize_text(country)
    if c is None:
        return None
    if c in _US_COUNTRY_ALIASES:
        return "us"
    return c


def normalize_state(state: Optional[str]) -> Optional[str]:
    """
    Normalize state/province.

    - If state is a 2-letter code -> return uppercase (e.g., "nc" -> "NC")
    - If state is a full US state name -> map to 2-letter code (e.g., "north carolina" -> "NC")
    - Otherwise return normalized text (useful for non-US provinces/regions)
    """
    s = normalize_text(state)
    if s is None:
        return None

    # Already a 2-letter code
    if re.fullmatch(r"[a-z]{2}", s):
        return s.upper()

    # Map common US state names
    mapped = _US_STATE_NAME_TO_CODE.get(s)
    if mapped:
        return mapped

    return s


def normalize_zip(zip_code: Optional[str]) -> Optional[str]:
    """
    Normalize to ZIP5 when possible.
    - "28277" -> "28277"
    - "28277-1234" -> "28277"
    - "282771234" -> "28277"
    """
    if zip_code is None:
        return None
    z = zip_code.strip()
    if not z:
        return None

    digits = re.sub(r"\D", "", z)
    if len(digits) >= 5:
        return digits[:5]  # ZIP5 for matching
    return digits or None


def normalize_unit_type(unit_type: Optional[str]) -> Optional[str]:
    if unit_type is None:
        return None
    t = normalize_text(unit_type)
    if t is None:
        return None
    return _UNIT_TYPE_SYNONYMS.get(t, t)


def normalize_unit_number(unit_number: Optional[str]) -> Optional[str]:
    # accepts USCISUnitType or free text
    if unit_number is None:
        return None
    u = unit_number.strip()
    if not u:
        return None
    # remove spaces, uppercase (2a -> 2A, " 2 A " -> "2A")
    u = re.sub(r"\s+", "", u).upper()
    # strip punctuation
    u = re.sub(r"[^A-Z0-9]", "", u)
    return u or None


def normalize_street(street: Optional[str]) -> Optional[str]:
    return normalize_text(street)


@dataclass(frozen=True)
class AddressKeys:
    """
    strict_key: includes unit + ZIP5 when available (strongest match)
    loose_key:  excludes unit and zip (useful for near-match detection)
    """
    strict_key: str
    loose_key: str


def address_keys(addr: PostalAddress) -> AddressKeys:
    """
    Build deterministic keys for matching addresses across people.

    strict_key includes:
      street | unit_type | unit_number | city | state | zip5 | country

    loose_key excludes unit and zip:
      street | city | state | country

    Missing fields become empty tokens (stable shape).
    """
    street = normalize_street(addr.street_name) or ""
    city = normalize_text(addr.city) or ""
    state = normalize_state(addr.state_province) or ""
    country = normalize_country(addr.country) or ""
    zip5 = normalize_zip(addr.zip_code) or ""

    unit_type = normalize_unit_type(addr.unit_type) or ""
    unit_number = normalize_unit_number(addr.unit_number) or ""

    strict = "|".join([street, unit_type, unit_number, city, state, zip5, country])
    loose = "|".join([street, city, state, country])

    return AddressKeys(strict_key=strict, loose_key=loose)


def compare_addresses(a: PostalAddress, b: PostalAddress) -> Tuple[bool, bool]:
    """
    Return (strict_match, loose_match).
    """
    ak = address_keys(a)
    bk = address_keys(b)
    strict_match = ak.strict_key == bk.strict_key
    loose_match = ak.loose_key == bk.loose_key
    return strict_match, loose_match
