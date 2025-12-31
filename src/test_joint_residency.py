# src/test_joint_residency.py

from datetime import date

from src.joint_residency import detect_joint_residency_start
from src.models import (
    AddressEntry,
    ImmigrationCase,
    PersonData,
    PostalAddress,
)


def addr(
    street: str,
    city: str = "Charlotte",
    state: str = "NC",
    zip_code: str = "28277",
    country: str = "USA",
    unit_type=None,
    unit_number=None,
) -> PostalAddress:
    return PostalAddress(
        street_name=street,
        unit_type=unit_type,
        unit_number=unit_number,
        city=city,
        state_province=state,
        zip_code=zip_code,
        country=country,
    )


def main():
    window_start = date(2022, 1, 1)
    window_end = date(2022, 12, 31)

    # -------------------------------------------------------
    # TEST 1: Strict match shared residence
    # Same address, same unit type, overlapping dates.
    # Expect: first_shared_date not None, match_type="strict", no issues.
    # -------------------------------------------------------
    pet = PersonData(
        addresses_lived=[
            AddressEntry(
                address=addr("1518 Asterwind Dr", unit_type="Apt", unit_number="2A"),
                date_from=date(2022, 6, 1),
                from_precision="day",
                date_to=date(2022, 9, 30),
                to_precision="day",
                address_type="lived",
            )
        ]
    )

    ben = PersonData(
        addresses_lived=[
            AddressEntry(
                address=addr("1518 Asterwind Dr", unit_type="Apt", unit_number="2A"),
                date_from=date(2022, 7, 1),
                from_precision="day",
                date_to=date(2022, 12, 31),
                to_precision="day",
                address_type="lived",
            )
        ]
    )

    case1 = ImmigrationCase(petitioner=pet, beneficiary=ben)
    r1 = detect_joint_residency_start(case1, window_start=window_start, window_end=window_end)

    print("\n=== TEST 1: Strict match ===")
    print("first_shared_date:", r1.first_shared_date)
    print("match_type:", r1.match_type)
    print("issues:", len(r1.issues))
    assert r1.first_shared_date == date(2022, 7, 1)
    assert r1.match_type == "strict"
    assert len(r1.issues) == 0

    # -------------------------------------------------------
    # TEST 2: Loose-only match (Apt vs Unit)
    # Same street/city/state/country, different unit_type -> strict false, loose true.
    # Expect: match_type="loose" and a medium issue.
    # -------------------------------------------------------
    pet2 = PersonData(
        addresses_lived=[
            AddressEntry(
                address=addr("1518 Asterwind Dr", unit_type="Apt", unit_number="2A"),
                date_from=date(2022, 6, 1),
                from_precision="day",
                date_to=date(2022, 9, 30),
                to_precision="day",
                address_type="lived",
            )
        ]
    )
    ben2 = PersonData(
        addresses_lived=[
            AddressEntry(
                address=addr("1518 Asterwind Dr", unit_type="Unit", unit_number="2a"),  # unit type differs
                date_from=date(2022, 7, 1),
                from_precision="day",
                date_to=date(2022, 12, 31),
                to_precision="day",
                address_type="lived",
            )
        ]
    )

    case2 = ImmigrationCase(petitioner=pet2, beneficiary=ben2)
    r2 = detect_joint_residency_start(case2, window_start=window_start, window_end=window_end)

    print("\n=== TEST 2: Loose-only match (Apt vs Unit) ===")
    print("first_shared_date:", r2.first_shared_date)
    print("match_type:", r2.match_type)
    for i in r2.issues:
        print(f"[{i.severity}] {i.message} (ref_id={i.ref_id})")
    assert r2.first_shared_date == date(2022, 7, 1)
    assert r2.match_type == "loose"
    assert any(i.severity == "medium" and i.category == "joint_residency" for i in r2.issues)

    # -------------------------------------------------------
    # TEST 3: No shared residence
    # Different streets, no overlap match.
    # Expect: first_shared_date=None and one medium issue.
    # -------------------------------------------------------
    pet3 = PersonData(
        addresses_lived=[
            AddressEntry(
                address=addr("111 First St", unit_type="Apt", unit_number="1A"),
                date_from=date(2022, 1, 1),
                from_precision="day",
                date_to=date(2022, 3, 31),
                to_precision="day",
                address_type="lived",
            )
        ]
    )
    ben3 = PersonData(
        addresses_lived=[
            AddressEntry(
                address=addr("999 Ninth St", unit_type="Apt", unit_number="9Z"),
                date_from=date(2022, 1, 1),
                from_precision="day",
                date_to=date(2022, 3, 31),
                to_precision="day",
                address_type="lived",
            )
        ]
    )

    case3 = ImmigrationCase(petitioner=pet3, beneficiary=ben3)
    r3 = detect_joint_residency_start(case3, window_start=window_start, window_end=window_end)

    print("\n=== TEST 3: No shared address ===")
    print("first_shared_date:", r3.first_shared_date)
    print("match_type:", r3.match_type)
    for i in r3.issues:
        print(f"[{i.severity}] {i.message} (ref_id={i.ref_id})")
    assert r3.first_shared_date is None
    assert r3.match_type is None
    assert len(r3.issues) == 1
    assert r3.issues[0].severity == "medium"

    print("\n✅ All joint residency tests passed.")


if __name__ == "__main__":
    main()
