# src/test_gaps.py

from datetime import date

from src.models import AddressEntry, PostalAddress
from src.validate import detect_address_gaps


def make_addr(street: str) -> PostalAddress:
    return PostalAddress(
        street_name=street,
        city="Charlotte",
        state_province="NC",
        zip_code="28209",
        country="USA",
    )


# We'll test a window that spans summer 2022
window_start = date(2022, 6, 1)
window_end = date(2022, 9, 30)

# -------------------------------------------------------
# TEST 1: Month precision should NOT create false gaps
# June 2022 -> July 2022 -> Aug 2022 -> Sep 2022
# All month-precision, so coverage should be continuous.
# -------------------------------------------------------
addresses_no_gap_month_precision = [
    AddressEntry(
        address=make_addr("111 First St"),
        date_from=date(2022, 6, 1),
        from_precision="month",
        date_to=date(2022, 6, 1),
        to_precision="month",
        address_type="lived",
        notes="June 2022 (month precision)",
    ),
    AddressEntry(
        address=make_addr("222 Second St"),
        date_from=date(2022, 7, 1),
        from_precision="month",
        date_to=date(2022, 7, 1),
        to_precision="month",
        address_type="lived",
        notes="July 2022 (month precision)",
    ),
    AddressEntry(
        address=make_addr("333 Third St"),
        date_from=date(2022, 8, 1),
        from_precision="month",
        date_to=date(2022, 8, 1),
        to_precision="month",
        address_type="lived",
        notes="Aug 2022 (month precision)",
    ),
    AddressEntry(
        address=make_addr("444 Fourth St"),
        date_from=date(2022, 9, 1),
        from_precision="month",
        date_to=date(2022, 9, 1),
        to_precision="month",
        address_type="lived",
        notes="Sep 2022 (month precision)",
    ),
]

issues = detect_address_gaps(
    addresses_no_gap_month_precision,
    window_start=window_start,
    window_end=window_end,
)

print("\n=== TEST 1: Month precision (should be NO gaps) ===")
if not issues:
    print("✅ No gaps detected (correct).")
else:
    print("❌ Unexpected gaps detected:")
    for i in issues:
        print(f"[{i.severity}] {i.message}")
        if i.suggested_question:
            print("  Q:", i.suggested_question)

# -------------------------------------------------------
# TEST 2: Day precision with an intentional 1-day gap
# Ends Jul 31, next starts Aug 2 -> gap Aug 1
# -------------------------------------------------------
addresses_gap_day_precision = [
    AddressEntry(
        address=make_addr("555 Fifth St"),
        date_from=date(2022, 6, 1),
        from_precision="day",
        date_to=date(2022, 7, 31),
        to_precision="day",
        address_type="lived",
        notes="Exact dates (day precision)",
    ),
    AddressEntry(
        address=make_addr("666 Sixth St"),
        date_from=date(2022, 8, 2),  # <-- intentional gap (Aug 1 missing)
        from_precision="day",
        date_to=date(2022, 9, 30),
        to_precision="day",
        address_type="lived",
        notes="Starts Aug 2 (day precision)",
    ),
]

issues2 = detect_address_gaps(
    addresses_gap_day_precision,
    window_start=window_start,
    window_end=window_end,
)

print("\n=== TEST 2: Day precision (should detect a gap on 2022-08-01) ===")
if not issues2:
    print("❌ No gaps detected (unexpected).")
else:
    for i in issues2:
        print(f"[{i.severity}] {i.message}")
        if i.suggested_question:
            print("  Q:", i.suggested_question)
