from datetime import date

from src.models import AddressEntry, PostalAddress
from src.validate import detect_address_overlaps


def make_addr(street: str) -> PostalAddress:
    return PostalAddress(
        street_name=street,
        city="Charlotte",
        state_province="NC",
        zip_code="28209",
        country="USA",
    )


window_start = date(2022, 6, 1)
window_end = date(2022, 9, 30)

# -------------------------------------------------------
# TEST 1: Day precision overlap
# Address A: Jun 1 -> Aug 15
# Address B: Aug 1 -> Sep 30
# Overlap: Aug 1 -> Aug 15
# -------------------------------------------------------
addresses_overlap_day_precision = [
    AddressEntry(
        address=make_addr("111 First St"),
        date_from=date(2022, 6, 1),
        from_precision="day",
        date_to=date(2022, 8, 15),
        to_precision="day",
        address_type="lived",
        notes="A ends Aug 15",
    ),
    AddressEntry(
        address=make_addr("222 Second St"),
        date_from=date(2022, 8, 1),
        from_precision="day",
        date_to=date(2022, 9, 30),
        to_precision="day",
        address_type="lived",
        notes="B starts Aug 1",
    ),
]

issues = detect_address_overlaps(
    addresses_overlap_day_precision,
    window_start=window_start,
    window_end=window_end,
)

print("\n=== TEST 1: Day precision overlap (should detect overlap Aug 1–Aug 15) ===")
if not issues:
    print("❌ No overlaps detected (unexpected).")
else:
    for i in issues:
        print(f"[{i.severity}] {i.message}")
        if i.suggested_question:
            print("  Q:", i.suggested_question)


# -------------------------------------------------------
# TEST 2: Month precision back-to-back (should NOT overlap)
# June 2022, July 2022, Aug 2022
# -------------------------------------------------------
addresses_no_overlap_month_precision = [
    AddressEntry(
        address=make_addr("333 Third St"),
        date_from=date(2022, 6, 1),
        from_precision="month",
        date_to=date(2022, 6, 1),
        to_precision="month",
        address_type="lived",
        notes="June 2022",
    ),
    AddressEntry(
        address=make_addr("444 Fourth St"),
        date_from=date(2022, 7, 1),
        from_precision="month",
        date_to=date(2022, 7, 1),
        to_precision="month",
        address_type="lived",
        notes="July 2022",
    ),
    AddressEntry(
        address=make_addr("555 Fifth St"),
        date_from=date(2022, 8, 1),
        from_precision="month",
        date_to=date(2022, 8, 1),
        to_precision="month",
        address_type="lived",
        notes="Aug 2022",
    ),
]

issues2 = detect_address_overlaps(
    addresses_no_overlap_month_precision,
    window_start=window_start,
    window_end=window_end,
)

print("\n=== TEST 2: Month precision (should be NO overlaps) ===")
if not issues2:
    print("✅ No overlaps detected (correct).")
else:
    print("❌ Unexpected overlaps detected:")
    for i in issues2:
        print(f"[{i.severity}] {i.message}")
        if i.suggested_question:
            print("  Q:", i.suggested_question)
