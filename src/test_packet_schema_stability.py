from datetime import date


from src.packet import (
    ALLOWED_TOPIC_NAMES,
    ALLOWED_RESOLUTION_TYPES,
    FINDING_CODE_REGISTRY,
    PACKET_SCHEMA_VERSION,
    build_attorney_review_packet,
)
from src.pipeline import load_case_from_json


def test_packet_includes_schema_version_and_uses_frozen_enums():
    """The attorney review packet must remain stable for downstream consumers."""

    today = date(2025, 12, 29)

    # Intentionally include data that triggers multiple issue categories.
    raw = {
        "beneficiary": {
            "addresses": [
                {
                    "street_name": "111 First St",
                    "city": "Charlotte",
                    "state_province": "North Carolina",  # triggers state formatting warning
                    "zip_code": "28209",
                    "country": "USA",
                    "date_from": "06/2022",
                    "date_to": "07/2022",
                    "address_type": "lived",
                },
            ],
            "employment": [
                {
                    "employer": "Vexa Consulting",
                    "role": "Analyst",
                    "date_from": "08/2025",
                    "date_to": "Present",
                    "employment_type": "self_employed",
                }
            ],
            "travel": [
                {
                    "event_type": "entry",
                    "date": "07/15/2023",
                    "port_or_city": "JFK",
                    "status_or_class": "B2",
                }
            ],
        },
        "petitioner": {"addresses": [], "employment": [], "travel": []},
        "marriage": {"date": "06/15/2025", "city": "Charlotte", "state": "NC", "country": "USA"},
    }

    result = load_case_from_json(raw, today=today)
    packet = build_attorney_review_packet(result)

    assert packet["meta"]["schema_version"] == PACKET_SCHEMA_VERSION

    # Topics must come from the frozen set.
    for item in packet.get("top_risks", {}).get("items", []):
        assert item["topic"] in ALLOWED_TOPIC_NAMES

        # Resolution types must come from the frozen set.
        assert item.get("resolution_type") in ALLOWED_RESOLUTION_TYPES

        # Finding codes must come from the frozen registry.
        codes = item.get("findings", {}).get("codes", []) or []
        for code in codes:
            assert code in FINDING_CODE_REGISTRY
