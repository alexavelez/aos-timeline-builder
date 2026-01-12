# src/test_exporters.py

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.exporters import export_packet_markdown, export_packet_pdf
from src.packet import build_attorney_review_packet
from src.pipeline import load_case_from_json


def _build_demo_packet():
    today = date(2025, 12, 29)
    raw = {
        "beneficiary": {
            "addresses": [
                {
                    "street_name": "111 First St",
                    "city": "Charlotte",
                    "state_province": "North Carolina",
                    "zip_code": "28209",
                    "country": "USA",
                    "date_from": "06/2022",
                    "date_to": "07/2022",
                    "address_type": "lived",
                },
                {
                    "street_name": "222 Second St",
                    "city": "Charlotte",
                    "state_province": "NC",
                    "zip_code": "28209",
                    "country": "USA",
                    "date_from": "2022-02-31",  # invalid
                    "date_to": "Present",
                    "address_type": "lived",
                },
            ],
            "employment": [
                {
                    "employer": "Vexa Consulting",
                    "role": "Analyst",
                    "date_from": "08/2025",
                    "date_to": "Present",
                    "employment_type": "self_employed",
                }
            ],
            "travel": [
                {
                    "event_type": "entry",
                    "date": "07/15/2023",
                    "port_or_city": "JFK",
                    "status_or_class": "B2",
                }
            ],
        },
        "petitioner": {"addresses": [], "employment": [], "travel": []},
        "marriage": {"date": "06/15/2025", "city": "Charlotte", "state": "NC", "country": "USA"},
    }
    result = load_case_from_json(raw, today=today)
    return build_attorney_review_packet(result)


def test_export_packet_markdown_smoke():
    packet = _build_demo_packet()
    md = export_packet_markdown(packet)
    assert "# Attorney Review Packet" in md
    assert "## Top Risks" in md
    # Should be copy/paste ready section if present
    assert "Client Clarification Pack" in md


def test_export_packet_pdf_smoke(tmp_path: Path):
    packet = _build_demo_packet()
    out = export_packet_pdf(packet, tmp_path / "packet.pdf")
    assert out.exists()
    assert out.stat().st_size > 500  # basic sanity check
