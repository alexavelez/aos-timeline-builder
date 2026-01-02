from datetime import date
from src.models import TravelEntry, EmploymentEntry
from src.travel_intelligence import analyze_travel


def test_two_entries_in_a_row_is_high():
    res = analyze_travel(
        [
            TravelEntry(event_type="entry", date=date(2020, 1, 10)),
            TravelEntry(event_type="entry", date=date(2020, 2, 10)),
        ],
        window_start=date(2020, 1, 1),
        window_end=date(2020, 12, 31),
    )
    assert any(i.severity == "high" and "Two entries in a row" in i.message for i in res.issues)


def test_unmatched_exit_is_high():
    res = analyze_travel(
        [TravelEntry(event_type="exit", date=date(2020, 6, 1))],
        window_start=date(2020, 1, 1),
        window_end=date(2020, 12, 31),
    )
    assert any(i.severity == "high" and "Exit recorded" in i.message for i in res.issues)


def test_entry_without_prior_exit_first_event_is_low():
    res = analyze_travel(
        [TravelEntry(event_type="entry", date=date(2020, 6, 1))],
        window_start=date(2020, 1, 1),
        window_end=date(2020, 12, 31),
    )
    assert any(i.severity == "low" and "First in-window travel event is an entry" in i.message for i in res.issues)


def test_entry_without_prior_exit_mid_window_is_high():
    res = analyze_travel(
        [
            TravelEntry(event_type="exit", date=date(2020, 1, 1)),
            TravelEntry(event_type="entry", date=date(2020, 1, 2)),
            TravelEntry(event_type="entry", date=date(2020, 2, 1)),  # entry without prior exit mid-window
        ],
        window_start=date(2020, 1, 1),
        window_end=date(2020, 12, 31),
    )
    assert any(i.severity == "high" and "without a preceding exit" in i.message for i in res.issues)


def test_long_absence_180_is_high():
    res = analyze_travel(
        [
            TravelEntry(event_type="exit", date=date(2020, 1, 1)),
            TravelEntry(event_type="entry", date=date(2020, 6, 28)),  # inclusive 180 days in 2020
        ],
        window_start=date(2020, 1, 1),
        window_end=date(2020, 12, 31),
    )
    assert any(i.severity == "high" and "Extended time outside" in i.message for i in res.issues)


def test_last_entry_missing_status_i94_inspected_is_high_when_inferred_in_us():
    res = analyze_travel(
        [TravelEntry(event_type="entry", date=date(2020, 6, 1))],
        window_start=date(2020, 1, 1),
        window_end=date(2020, 12, 31),
    )
    # should flag missing inspected + missing status + missing i94
    assert any(i.severity == "high" and "missing whether you were inspected" in i.message for i in res.issues)
    assert any(i.severity == "high" and "missing class of admission" in i.message for i in res.issues)
    assert any(i.severity == "high" and "missing I-94 number" in i.message for i in res.issues)


def test_travel_overlaps_employment_flags():
    travel = [
        TravelEntry(event_type="exit", date=date(2020, 2, 1)),
        TravelEntry(event_type="entry", date=date(2020, 5, 1)),
    ]
    emp = [
        EmploymentEntry(
            employer="ACME",
            date_from=date(2020, 1, 1),
            from_precision="day",
            date_to=date(2020, 12, 31),
            to_precision="day",
            employment_type="employed",
        )
    ]
    res = analyze_travel(
        travel,
        window_start=date(2020, 1, 1),
        window_end=date(2020, 12, 31),
        employment=emp,
    )
    assert any("overlaps an active" in i.message for i in res.issues)
