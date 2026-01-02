# src/test_canonicalize.py

from src.canonicalize import address_keys, compare_addresses
from src.models import PostalAddress


def main():
    # Same underlying place, different formatting
    a = PostalAddress(
        street_name="1518 Asterwind Dr.",
        unit_type="Apt",
        unit_number="2A",
        city="Charlotte",
        state_province="NC",
        zip_code="28277",
        country="USA",
    )

    b = PostalAddress(
        street_name="1518  Asterwind  Dr",  # extra spaces, no punctuation
        unit_type="Unit",                    # different unit type
        unit_number=" 2a ",                  # spacing + casing
        city="CHARLOTTE",
        state_province="North Carolina",     # full name (not auto-mapped yet)
        zip_code="28277-1234",               # 9-digit ZIP formatting
        country="United States",
    )

    ak = address_keys(a)
    bk = address_keys(b)

    print("\n=== Keys A ===")
    print("strict:", ak.strict_key)
    print("loose: ", ak.loose_key)

    print("\n=== Keys B ===")
    print("strict:", bk.strict_key)
    print("loose: ", bk.loose_key)

    strict_match, loose_match = compare_addresses(a, b)

    print("\n=== Compare ===")
    print("strict_match:", strict_match)
    print("loose_match: ", loose_match)

    # What we EXPECT for MVP:
    # - loose should match (street/city/state/country after normalization)
    # - strict likely won't match because:
    #     unit_type differs (apt vs unit)
    #     state full-name isn't mapped to "NC" yet
    #     zip becomes digits-only; that part matches, but state token differs
    #
    # If you later add state name -> code mapping and unit-type collapsing rules,
    # you can tighten strict matching.

    assert loose_match is True, "Expected loose match for near-identical addresses"
    print("\n✅ Canonicalization smoke test passed.")


if __name__ == "__main__":
    main()
