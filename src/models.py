# src/models.py

from __future__ import annotations

from datetime import date
from typing import Optional, List, Literal

from pydantic import BaseModel, Field


# ======================================================
# Controlled sets (USCIS-aligned)
# ======================================================

USCISUnitType = Literal["Apt", "Ste", "Fl", "Unit"]

AddressType = Literal["lived", "temporary", "mailing"]
EmploymentType = Literal["employed", "self_employed", "unemployed"]
TravelEventType = Literal["entry", "exit"]

RelatedPurpose = Literal[
    "employer_location",
    "relative_home",
    "used_on_application",
    "mailing",
    "other",
]


# ======================================================
# Name model (IMPORTANT for USCIS)
# ======================================================

class PersonName(BaseModel):
    """
    USCIS-aligned name structure.
    USCIS always separates First / Middle / Last.
    For cultures with two last names, both go in last_name.
    """
    first_name: str
    middle_name: Optional[str] = None
    last_name: str

    # Aliases, maiden names, alternate spellings, etc.
    other_names_used: List[str] = Field(default_factory=list)


# ======================================================
# Reusable postal address
# ======================================================

class PostalAddress(BaseModel):
    street_name: str
    unit_type: Optional[USCISUnitType] = None
    unit_number: Optional[str] = None

    city: str
    state_province: Optional[str] = None
    zip_code: Optional[str] = None
    country: str


# ======================================================
# Address timeline (where a person lived)
# ======================================================

class AddressEntry(BaseModel):
    """
    Residential address history entry.
    date_to=None means "Present".
    """
    address: PostalAddress
    date_from: date
    date_to: Optional[date] = None
    address_type: AddressType = "lived"
    notes: Optional[str] = None


class RelatedAddress(BaseModel):
    """
    Addresses relevant to the case but not part of the residential timeline.
    """
    address: PostalAddress
    purpose: RelatedPurpose
    related_to: Optional[str] = None
    notes: Optional[str] = None


# ======================================================
# Employment and travel
# ======================================================

class EmploymentEntry(BaseModel):
    employer: str
    role: Optional[str] = None
    employer_address: Optional[PostalAddress] = None

    date_from: date
    date_to: Optional[date] = None
    employment_type: EmploymentType
    notes: Optional[str] = None


class TravelEntry(BaseModel):
    event_type: TravelEventType
    date: date
    port_or_city: Optional[str] = None
    status_or_class: Optional[str] = None
    notes: Optional[str] = None


# ======================================================
# Person-level container
# ======================================================

class PersonData(BaseModel):
    """
    Data for ONE person (petitioner or beneficiary).
    """
    name: Optional[PersonName] = None

    # Residential timeline (typically last 5 years)
    addresses_lived: List[AddressEntry] = Field(default_factory=list)

    # Non-timeline addresses (FYI / disclosure)
    related_addresses: List[RelatedAddress] = Field(default_factory=list)

    # USCIS-required anchor (may be older than timeline)
    last_foreign_address: Optional[PostalAddress] = None
    last_foreign_address_date_to: Optional[date] = None

    employment: List[EmploymentEntry] = Field(default_factory=list)
    travel_entries: List[TravelEntry] = Field(default_factory=list)


# ======================================================
# Case wrapper (marriage-based AOS)
# ======================================================

class ImmigrationCase(BaseModel):
    """
    Marriage-based adjustment case.
    Keeps petitioner and beneficiary clearly separated.
    """
    petitioner: PersonData
    beneficiary: PersonData


# ======================================================
# Sanity test
# ======================================================

if __name__ == "__main__":
    case = ImmigrationCase(
        petitioner=PersonData(
            name=PersonName(
                first_name="John",
                last_name="Smith",
            )
        ),
        beneficiary=PersonData(
            name=PersonName(
                first_name="Jane",
                middle_name="Ann",
                last_name="Doe",
                other_names_used=["Jane Doe"],
            ),
            last_foreign_address=PostalAddress(
                street_name="Calle 100 # 10-20",
                unit_type="Apt",
                unit_number="55",
                city="Springfield",
                state_province="Central Province",
                zip_code="000000",
                country="Colombia",
            ),
        ),
    )

    print(case.model_dump())
