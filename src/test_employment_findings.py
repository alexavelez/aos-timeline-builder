from datetime import date
from src.models import EmploymentEntry
from src.validate import detect_employment_gaps
from src.packet import build_flagged_item_summary


def test_employment_window_start_missing_finding():
    employment = [
        EmploymentEntry(
            employer="ACME",
            role="Analyst",
            date_from=date(2022, 2, 1),
            from_precision="day",
            date_to=date(2022, 12, 31),
            to_precision="day",
            employment_type="employed",
        )
    ]

    window_start = date(2022, 1, 1)
    window_end = date(2022, 12, 31)

    issues = detect_employment_gaps(employment, window_start=window_start, window_end=window_end)
    top = build_flagged_item_summary(issues, n=3)
    assert "employment_window_start_missing" in top[0]["findings"]["codes"]


def test_employment_window_end_missing_finding():
    employment = [
        EmploymentEntry(
            employer="ACME",
            role="Analyst",
            date_from=date(2022, 1, 1),
            from_precision="day",
            date_to=date(2022, 10, 1),
            to_precision="day",
            employment_type="employed",
        )
    ]

    window_start = date(2022, 1, 1)
    window_end = date(2022, 12, 31)

    issues = detect_employment_gaps(employment, window_start=window_start, window_end=window_end)
    top = build_flagged_item_summary(issues, n=3)
    assert "employment_window_end_missing" in top[0]["findings"]["codes"]
