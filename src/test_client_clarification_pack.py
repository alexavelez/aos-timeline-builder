from src.validate import Issue
from src.packet import build_client_clarification_pack


def test_client_clarification_pack_dedupes_and_prioritizes():
    q = "Where did you live from 2022-08-01 to 2022-08-01?"

    issues = [
        Issue(
            severity="high",
            category="address_history",
            message="Unexplained address gap of 1 day(s): 2022-08-01 to 2022-08-01.",
            suggested_question=q,
            ref_id="ben_address_history",
        ),
        # Duplicate question should be deduped
        Issue(
            severity="medium",
            category="address_history",
            message="Address gap at the start of the window: 2022-08-01 to 2022-08-01.",
            suggested_question=q,
            ref_id="ben_address_history",
        ),
        # Another topic
        Issue(
            severity="medium",
            category="employment",
            message="Unexplained employment gap of 10 day(s): 2023-01-01 to 2023-01-10.",
            suggested_question="What were you doing from 2023-01-01 to 2023-01-10 (employed, unemployed, or self-employed)?",
            ref_id="ben_employment_history",
        ),
    ]

    pack = build_client_clarification_pack(issues)

    assert pack["summary"]["total_questions"] == 2
    # Highest priority comes first
    assert pack["questions"][0]["priority"] == "P0"
    assert pack["questions"][0]["topic"] == "address"
    assert "2022-08-01" in pack["questions"][0]["prompt"]

    # Email body is generated and contains both sections
    body = pack["email"]["body"]
    assert "Address history" in body
    assert "Employment history" in body
    assert "[REQUIRED]" in body
