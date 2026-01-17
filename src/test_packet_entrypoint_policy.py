from src.packet import build_packet_from_json
from src.policy import FirmPolicy


def test_packet_entrypoint_threads_policy_top_n():
    raw = {
        "petitioner": {"addresses": [], "employment": [], "travel": []},
        "beneficiary": {"addresses": [], "employment": [], "travel": []},
        "marriage": {"date": "2024-01-01"},
    }

    packet = build_packet_from_json(raw, policy=FirmPolicy(executive_summary_top_n=3))

    top_risks = packet.get("executive_summary", {}).get("top_risks", [])
    assert len(top_risks) <= 3
    assert packet["policy_meta"]["source"] == "object"
