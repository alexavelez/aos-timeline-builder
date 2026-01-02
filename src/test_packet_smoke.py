# src/test_packet_smoke.py

from datetime import date
import json

from src.pipeline import load_case_from_json
from src.packet import build_attorney_review_packet


def main():
    today = date(2025, 12, 29)

    raw = {
        "beneficiary": {
            "addresses": [
                {
                    "street_name": "111 First St",
                    "city": "Charlotte",
                    "state_province": "North Carolina",
                    "zip_code": "28209",
                    "country": "USA",
                    "date_from": "06/2022",
                    "date_to": "07/2022",
                    "address_type": "lived",
                },
                {
                    "street_name": "222 Second St",
                    "city": "Charlotte",
                    "state_province": "NC",
                    "zip_code": "28209",
                    "country": "USA",
                    "date_from": "2022-02-31",  # invalid
                    "date_to": "Present",
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

    # Pretty print a short version
    print(json.dumps(packet["issues"]["counts"], indent=2))
    print("\nSample HIGH issue (if any):")
    highs = packet["issues"]["by_severity"]["high"]
    if highs:
        print(json.dumps(highs[0], indent=2))
    else:
        print("No high issues.")

    print("\nTimelines summary:")
    print("Beneficiary addresses:", len(packet["timelines"]["beneficiary"]["addresses_lived"]))
    print("Beneficiary employment:", len(packet["timelines"]["beneficiary"]["employment"]))
    print("Beneficiary travel:", len(packet["timelines"]["beneficiary"]["travel"]))


if __name__ == "__main__":
    main()
