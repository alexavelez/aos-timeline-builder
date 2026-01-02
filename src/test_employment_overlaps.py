from datetime import date
from src.models import EmploymentEntry
from src.validate import detect_employment_overlaps


def test_employment_overlap_one_day_is_low():
    window_start = date(2020, 1, 1)
    window_end = date(2020, 1, 10)

    emp = [
        EmploymentEntry(
            employer="A",
            date_from=date(2020, 1, 1),
            from_precision="day",
            date_to=date(2020, 1, 5),
            to_precision="day",
            employment_type="employed",
        ),
        EmploymentEntry(
            employer="B",
            date_from=date(2020, 1, 5),  # overlaps by 1 day (Jan 5)
            from_precision="day",
            date_to=date(2020, 1, 10),
            to_precision="day",
            employment_type="employed",
        ),
    ]

    issues = detect_employment_overlaps(emp, window_start=window_start, window_end=window_end)
    assert len(issues) == 1
    assert issues[0].severity == "low"


def test_employment_overlap_long_is_high():
    window_start = date(2020, 1, 1)
    window_end = date(2020, 3, 31)

    emp = [
        EmploymentEntry(
            employer="A",
            date_from=date(2020, 1, 1),
            from_precision="day",
            date_to=date(2020, 3, 1),
            to_precision="day",
            employment_type="employed",
        ),
        EmploymentEntry(
            employer="B",
            date_from=date(2020, 2, 1),  # overlaps 2/1 through 3/1 (30 days in 2020 leap year Feb? actually 2/1-3/1 inclusive = 30)
            from_precision="day",
            date_to=date(2020, 3, 31),
            to_precision="day",
            employment_type="employed",
        ),
    ]

    issues = detect_employment_overlaps(emp, window_start=window_start, window_end=window_end)
    assert len(issues) == 1
    assert issues[0].severity == "high"


def test_employment_overlap_with_month_precision_detects_overlap():
    window_start = date(2020, 1, 1)
    window_end = date(2020, 12, 31)

    emp = [
        EmploymentEntry(
            employer="A",
            date_from=date(2020, 1, 1),
            from_precision="month",  # covers Jan 1 - Jan 31
            date_to=date(2020, 1, 1),
            to_precision="month",
            employment_type="employed",
        ),
        EmploymentEntry(
            employer="B",
            date_from=date(2020, 1, 1),
            from_precision="month",
            date_to=date(2020, 2, 1),
            to_precision="month",
            employment_type="employed",
        ),
    ]

    issues = detect_employment_overlaps(emp, window_start=window_start, window_end=window_end)
    assert len(issues) == 1
