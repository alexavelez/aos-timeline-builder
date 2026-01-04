# src/test_top_risks.py

from src.validate import Issue
from src.packet import build_top_risk_summary


def test_top_risks_ranking_prefers_travel_admission():
    issues = [
        Issue(
            severity="high",
            category="travel",
            message="Last entry on 2020-01-01 is missing I-94 number.",
            suggested_question="Provide I-94.",
            ref_id="ben_travel_history",
        ),
        Issue(
            severity="medium",
            category="address_history",
            message="Unexplained address gap of 1 day(s): 2020-02-01 to 2020-02-01.",
            suggested_question="Where did you live?",
            ref_id="ben_addr_0",
        ),
        Issue(
            severity="medium",
            category="address_history",
            message="For U.S. addresses, USCIS prefers 2-letter state codes. You entered 'North Carolina'.",
            suggested_question="Confirm state code.",
            ref_id="ben_addr_1",
        ),
    ]

    top = build_top_risk_summary(issues, n=3)
    assert top[0]["topic"] == "travel_admission"
    assert top[0]["severity"] == "high"
    assert top[0]["issue_count"] == 1


def test_top_risks_clusters_address_continuity():
    issues = [
        Issue(severity="high", category="address_history", message="Address gap at the start of the window: ...", ref_id="a"),
        Issue(severity="high", category="address_history", message="Address gap at the end of the window: ...", ref_id="b"),
        Issue(severity="medium", category="address_history", message="Overlapping residential addresses for 2 day(s): ...", ref_id="c"),
    ]
    top = build_top_risk_summary(issues, n=5)
    topics = [t["topic"] for t in top]
    assert "address_continuity" in topics
    # address_continuity should appear once, not three times (clustered)
    assert topics.count("address_continuity") == 1
