# src/test_risk_narratives.py

from src.validate import Issue
from src.packet import build_flagged_item_summary, add_flagged_item_narratives


def test_risk_narrative_structure_and_rendered_text():
    issues = [
        Issue(
            severity="high",
            category="travel",
            message="Last entry on 2020-01-01 is missing I-94 number.",
            suggested_question="Please provide the I-94 number for your last entry.",
            ref_id="ben_travel_history",
        ),
        Issue(
            severity="high",
            category="travel",
            message="Last entry on 2020-01-01 is missing class of admission/status.",
            suggested_question="Please provide the class of admission for your last entry.",
            ref_id="ben_travel_history",
        ),
    ]

    top = build_flagged_item_summary(issues, n=3)
    enriched = add_flagged_item_narratives(top)

    assert len(enriched) >= 1
    item0 = enriched[0]
    assert "narrative" in item0

    nar = item0["narrative"]
    # Structured fields exist
    assert isinstance(nar.get("summary_points"), list)
    assert isinstance(nar.get("action_items"), list)
    assert isinstance(nar.get("client_questions"), list)
    assert isinstance(nar.get("evidence_targets"), list)
    assert isinstance(nar.get("refs"), list)

    # Rendered text exists and mentions key section headers
    rendered = nar.get("rendered_text", "")
    assert "Why it matters:" in rendered
    assert "Recommended actions:" in rendered
    assert "Client questions:" in rendered
