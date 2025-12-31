from datetime import date
from src.models import EmploymentEntry
from src.validate import detect_employment_gaps

def test_employment_gaps_none_provided_is_high():
    issues = detect_employment_gaps([], window_start=date(2020,1,1), window_end=date(2020,12,31))
    assert len(issues) == 1
    assert issues[0].severity == "high"
    assert issues[0].category == "employment"

def test_employment_gap_middle_one_day_is_medium():
    window_start = date(2020,1,1)
    window_end = date(2020,1,10)

    emp = [
        EmploymentEntry(
            employer="A",
            date_from=date(2020,1,1),
            from_precision="day",
            date_to=date(2020,1,4),
            to_precision="day",
            employment_type="employed",
        ),
        EmploymentEntry(
            employer="B",
            date_from=date(2020,1,6),
            from_precision="day",
            date_to=date(2020,1,10),
            to_precision="day",
            employment_type="employed",
        ),
    ]
    issues = detect_employment_gaps(emp, window_start=window_start, window_end=window_end)
    assert len(issues) == 1
    assert issues[0].severity == "medium"
    assert "2020-01-05" in issues[0].message

def test_employment_precision_month_avoids_false_gap():
    window_start = date(2020,1,1)
    window_end = date(2020,12,31)

    # Jan 2020 through Mar 2020 (month precision)
    emp = [
        EmploymentEntry(
            employer="A",
            date_from=date(2020,1,1),
            from_precision="month",
            date_to=date(2020,3,1),
            to_precision="month",
            employment_type="employed",
        ),
        # Apr 2020 onward (month precision)
        EmploymentEntry(
            employer="B",
            date_from=date(2020,4,1),
            from_precision="month",
            date_to=date(2020,12,1),
            to_precision="month",
            employment_type="employed",
        ),
    ]
    # There should be no gap because Mar month precision covers through 03/31 and Apr starts 04/01
    issues = detect_employment_gaps(emp, window_start=window_start, window_end=window_end)
    assert issues == []
