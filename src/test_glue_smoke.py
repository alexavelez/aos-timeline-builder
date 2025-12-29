from src.glue import parse_address_list, parse_employment_list, parse_travel_list


def print_issues(title: str, issues):
    print(f"\n=== {title} ===")
    if not issues:
        print("✅ No issues")
        return
    for i in issues:
        # Issue now has ref_id
        print(f"[{i.severity}] ({i.category}) ref_id={i.ref_id} :: {i.message}")
        if i.suggested_question:
            print("  Q:", i.suggested_question)


def main():
    # ----------------------------
    # Addresses
    # ----------------------------
    raw_addresses = [
        {
            "street_name": "111 First St",
            "city": "Charlotte",
            "state_province": "North Carolina",  # <-- should warn (US state not 2-letter)
            "zip_code": "28209",
            "country": "USA",
            "date_from": "06/2022",
            "date_to": "07/2022",
            "address_type": "lived",
        },
        {
            "street_name": "222 Second St",
            "city": "Charlotte",
            "state_province": "NC",  # ok
            "zip_code": "28209",
            "country": "USA",
            "date_from": "2022-02-31",  # <-- invalid date (should be high issue)
            "date_to": "Present",
            "address_type": "lived",
        },
    ]

    addr_entries, addr_issues, addr_snaps = parse_address_list(raw_addresses)

    print("\n=== Parsed Address Entries ===")
    for e in addr_entries:
        print(f"- {e.address.street_name}, {e.address.city}, {e.address.state_province} | "
              f"{e.date_from} ({e.from_precision}) -> {e.date_to} ({e.to_precision})")

    print("\n=== Address Snapshots ===")
    for s in addr_snaps:
        print(f"- snapshot_id={s.id}, section={s.section}, raw_keys={list(s.raw.keys())}")

    print_issues("Address Issues (expect ref_id=addr_0 and addr_1)", addr_issues)

    # ----------------------------
    # Employment
    # ----------------------------
    raw_employment = [
        {
            "employer": "Vexa Consulting",
            "role": "Analyst",
            "date_from": "08/2025",
            "date_to": "Present",
            "employment_type": "self_employed",
        },
        {
            "employer": "",  # missing
            "date_from": "bad-date",  # invalid
            "date_to": "Present",
            "employment_type": "employed",
        },
    ]

    emp_entries, emp_issues, emp_snaps = parse_employment_list(raw_employment)

    print("\n=== Parsed Employment Entries ===")
    for e in emp_entries:
        print(f"- {e.employer} | {e.date_from} -> {e.date_to} | {e.employment_type}")

    print("\n=== Employment Snapshots ===")
    for s in emp_snaps:
        print(f"- snapshot_id={s.id}, section={s.section}, raw_keys={list(s.raw.keys())}")

    print_issues("Employment Issues (expect ref_id=emp_1)", emp_issues)

    # ----------------------------
    # Travel
    # ----------------------------
    raw_travel = [
        {
            "event_type": "entry",
            "date": "07/15/2023",
            "port_or_city": "JFK",
            "status_or_class": "B2",
        },
        {
            "event_type": "return",  # invalid
            "date": "Present",       # not allowed for travel date
            "port_or_city": "MIA",
        },
    ]

    trv_entries, trv_issues, trv_snaps = parse_travel_list(raw_travel)

    print("\n=== Parsed Travel Entries ===")
    for e in trv_entries:
        print(f"- {e.event_type} on {e.date} | {e.port_or_city} | {e.status_or_class}")

    print("\n=== Travel Snapshots ===")
    for s in trv_snaps:
        print(f"- snapshot_id={s.id}, section={s.section}, raw_keys={list(s.raw.keys())}")

    print_issues("Travel Issues (expect ref_id=trv_1)", trv_issues)


if __name__ == "__main__":
    main()
