# src/test_pipeline_smoke.py

from datetime import date

from src.pipeline import load_case_from_json


def main():
    # Use a fixed "today" so results are deterministic
    today = date(2025, 12, 29)

    raw = {
        "beneficiary": {
            "addresses": [
                {
                    "street_name": "111 First St",
                    "city": "Charlotte",
                    "state_province": "North Carolina",  # warns (US code)
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
                    "date_from": "2022-02-31",  # invalid -> high issue
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
        "petitioner": {
            "addresses": [],
            "employment": [],
            "travel": [],
        },
        "marriage": {
            "date": "06/15/2025",
            "city": "Charlotte",
            "state": "NC",
            "country": "USA",
        },
    }

    result = load_case_from_json(raw, today=today, validate_petitioner=False)

    print("\n=== Window ===")
    print("start:", result.window_start)
    print("end:  ", result.window_end)

    print("\n=== Case (summary) ===")
    print("marriage_date:", result.case.marriage_date)
    print("beneficiary addresses parsed:", len(result.case.beneficiary.addresses_lived))
    print("beneficiary employment parsed:", len(result.case.beneficiary.employment))
    print("beneficiary travel parsed:", len(result.case.beneficiary.travel_entries))

    print("\n=== Snapshots ===")
    for s in result.snapshots:
        print(f"- id={s.id} section={s.section} keys={list(s.raw.keys())}")

    print("\n=== Issues ===")
    for i in result.issues:
        print(f"[{i.severity}] ({i.category}) ref_id={i.ref_id} :: {i.message}")
        if i.suggested_question:
            print("  Q:", i.suggested_question)


if __name__ == "__main__":
    main()
