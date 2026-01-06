from datetime import date
from src.models import AddressEntry, PostalAddress
from src.validate import detect_address_gaps
from src.packet import build_top_risk_summary


def test_address_window_start_missing_finding():
    # Covers only mid-window, leaving a start gap
    addresses = [
        AddressEntry(
            address=PostalAddress(
                street_name="1 Main St",
                city="Charlotte",
                state_province="NC",
                zip_code="28209",
                country="USA",
            ),
            date_from=date(2022, 2, 1),
            from_precision="day",
            date_to=date(2022, 12, 31),
            to_precision="day",
            address_type="lived",
        )
    ]

    window_start = date(2022, 1, 1)
    window_end = date(2022, 12, 31)

    issues = detect_address_gaps(addresses, window_start=window_start, window_end=window_end)
    top = build_top_risk_summary(issues, n=3)

    findings = top[0]["findings"]["codes"]
    assert "address_window_start_missing" in findings


def test_address_window_end_missing_finding():
    # Covers only early window, leaving an end gap
    addresses = [
        AddressEntry(
            address=PostalAddress(
                street_name="1 Main St",
                city="Charlotte",
                state_province="NC",
                zip_code="28209",
                country="USA",
            ),
            date_from=date(2022, 1, 1),
            from_precision="day",
            date_to=date(2022, 10, 1),
            to_precision="day",
            address_type="lived",
        )
    ]

    window_start = date(2022, 1, 1)
    window_end = date(2022, 12, 31)

    issues = detect_address_gaps(addresses, window_start=window_start, window_end=window_end)
    top = build_top_risk_summary(issues, n=3)

    findings = top[0]["findings"]["codes"]
    assert "address_window_end_missing" in findings
