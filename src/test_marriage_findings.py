from src.validate import Issue
from src.packet import build_top_risk_summary


def test_no_shared_residence_near_marriage_finding_and_resolution():
    issues = [
        Issue(
            severity="medium",
            category="marriage",
            message=(
                "No shared residential address overlap was detected around the marriage date (2024-01-01 to 2024-06-29)."
            ),
        )
    ]
    top = build_top_risk_summary(issues, n=3)
    assert top[0]["topic"] == "marriage"
    assert "no_shared_residence_near_marriage" in top[0]["findings"]["codes"]
    assert top[0]["resolution_type"] == "prepare_evidence"


def test_long_separation_near_marriage_finding_and_resolution():
    issues = [
        Issue(
            severity="medium",
            category="marriage",
            message=(
                "Extended travel separation was detected near the marriage date (2024-01-01 to 2024-06-29). Beneficiary travel: 2024-02-01 to 2024-05-11 (100 days)"
            ),
        )
    ]
    top = build_top_risk_summary(issues, n=3)
    assert top[0]["topic"] == "marriage"
    assert "long_separation_near_marriage" in top[0]["findings"]["codes"]
    assert top[0]["resolution_type"] == "prepare_evidence"
