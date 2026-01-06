from src.validate import Issue
from src.packet import build_top_risk_summary


def _top_codes(issues):
    top = build_top_risk_summary(issues, n=3)
    return top[0]["findings"]["codes"]


def test_missing_i94_last_entry_finding():
    issues = [Issue(severity="high", category="travel", message="Last entry on 2024-01-01 is missing I-94 number.")]
    assert "missing_i94_last_entry" in _top_codes(issues)


def test_missing_class_last_entry_finding():
    issues = [Issue(severity="high", category="travel", message="Last entry on 2024-01-01 is missing class of admission/status.")]
    assert "missing_class_of_admission_last_entry" in _top_codes(issues)


def test_missing_inspection_last_entry_finding():
    issues = [Issue(severity="high", category="travel", message="Last entry on 2024-01-01 is missing whether you were inspected/admitted/paroled.")]
    assert "missing_inspection_flag_last_entry" in _top_codes(issues)


def test_not_inspected_last_entry_finding():
    issues = [Issue(severity="high", category="travel", message="Last entry on 2024-01-01 indicates NOT inspected/admitted/paroled.")]
    assert "not_inspected_last_entry" in _top_codes(issues)
