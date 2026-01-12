from datetime import date


from src.packet import build_attorney_review_packet
from src.pipeline import load_case_from_json


def _find_topic_item(packet: dict, topic: str) -> dict | None:
    for item in packet.get("top_risks", {}).get("items", []):
        if item.get("topic") == topic:
            return item
    return None


def test_employment_long_absence_flags_beneficiary_and_petitioner_differently():
    """Beneficiary gets compliance-aware flag; petitioner gets consistency-only flag."""

    today = date(2025, 12, 29)

    raw = {
        "beneficiary": {
            "addresses": [],
            "employment": [
                {
                    "employer": "Acme Corp",
                    "role": "Analyst",
                    "date_from": "01/01/2023",
                    "date_to": "12/31/2023",
                    "employment_type": "employed",
                }
            ],
            "travel": [
                {"event_type": "exit", "date": "02/01/2023", "port_or_city": "JFK"},
                {"event_type": "entry", "date": "09/01/2023", "port_or_city": "JFK", "status_or_class": "B2"},
            ],
        },
        "petitioner": {
            "addresses": [],
            "employment": [
                {
                    "employer": "Beta LLC",
                    "role": "Manager",
                    "date_from": "01/2023",
                    "date_to": "12/2023",
                    "employment_type": "employed",
                }
            ],
            "travel": [
                {"event_type": "exit", "date": "02/01/2023", "port_or_city": "JFK"},
                {"event_type": "entry", "date": "09/01/2023", "port_or_city": "JFK"},
            ],
        },
        "marriage": {"date": "06/15/2025", "city": "Charlotte", "state": "NC", "country": "USA"},
    }

    result = load_case_from_json(raw, today=today, validate_petitioner=True)
    packet = build_attorney_review_packet(result)

    # Ensure petitioner does NOT get compliance-aware wording.
    petitioner_msgs = [i.message.lower() for i in result.issues if (i.ref_id or "") == "pet_employment_history"]
    assert all("work authorization" not in m for m in petitioner_msgs)

    employment_item = _find_topic_item(packet, "employment")
    assert employment_item is not None

    codes = set((employment_item.get("findings", {}) or {}).get("codes", []) or [])
    assert "employment_during_long_absence" in codes
    assert "possible_unauthorized_work_risk" in codes


def test_short_absence_does_not_trigger_employment_long_absence_flags():
    today = date(2025, 12, 29)

    raw = {
        "beneficiary": {
            "addresses": [],
            "employment": [
                {
                    "employer": "Acme Corp",
                    "role": "Analyst",
                    "date_from": "01/01/2024",
                    "date_to": "12/31/2024",
                    "employment_type": "employed",
                }
            ],
            "travel": [
                {"event_type": "exit", "date": "06/01/2024", "port_or_city": "JFK"},
                {"event_type": "entry", "date": "06/15/2024", "port_or_city": "JFK"},
            ],
        },
        "petitioner": {"addresses": [], "employment": [], "travel": []},
        "marriage": {"date": "06/15/2025", "city": "Charlotte", "state": "NC", "country": "USA"},
    }

    result = load_case_from_json(raw, today=today)
    packet = build_attorney_review_packet(result)

    employment_item = _find_topic_item(packet, "employment")
    if employment_item is None:
        return
    codes = set((employment_item.get("findings", {}) or {}).get("codes", []) or [])
    assert "employment_during_long_absence" not in codes
    assert "possible_unauthorized_work_risk" not in codes
