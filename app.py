"""
AOS Timeline Builder - Streamlit app

Wires user-provided case data into the existing analysis pipeline
(src.packet.build_packet_from_json) and renders the resulting attorney
review packet: an executive summary, full review/issue detail, a
copy/paste-ready client clarification email, and raw timelines.
Also offers Markdown/PDF export of the same packet.

Case data can be entered two ways:
  - "Build a case": a guided form (no JSON knowledge required)
  - "Paste JSON": raw JSON, useful for testing or reusing a saved case
"""

from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

import streamlit as st

from src.packet import build_packet_from_json
from src.exporters import export_packet_markdown, export_packet_pdf


SAMPLE_CASE = {
    "beneficiary": {
        "addresses": [
            {
                "street_name": "111 First St",
                "city": "Charlotte",
                "state_province": "NC",
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
                "date_from": "08/2022",
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
            {"event_type": "exit", "date": "02/01/2023", "port_or_city": "JFK"},
            {
                "event_type": "entry",
                "date": "07/15/2023",
                "port_or_city": "JFK",
                "status_or_class": "B2",
            },
        ],
    },
    "petitioner": {
        "addresses": [
            {
                "street_name": "222 Second St",
                "city": "Charlotte",
                "state_province": "NC",
                "zip_code": "28209",
                "country": "USA",
                "date_from": "01/2021",
                "date_to": "Present",
                "address_type": "lived",
            }
        ],
        "employment": [
            {
                "employer": "Beta LLC",
                "role": "Manager",
                "date_from": "01/2023",
                "date_to": "Present",
                "employment_type": "employed",
            }
        ],
        "travel": [],
    },
    "marriage": {
        "date": "06/15/2025",
        "city": "Charlotte",
        "state": "NC",
        "country": "USA",
    },
}

SEVERITY_BADGE = {"high": "\U0001F534", "medium": "\U0001F7E0", "low": "\U0001F7E1"}

ADDRESS_TYPES = ["lived", "temporary", "mailing"]
EMPLOYMENT_TYPES = ["employed", "self_employed", "unemployed"]
UNIT_TYPES = ["", "Apt", "Ste", "Fl", "Unit"]
TRAVEL_EVENT_TYPES = ["entry", "exit"]


# ---------------------------------------------------------------------------
# Case builder form (no JSON knowledge required)
# ---------------------------------------------------------------------------


def _next_id() -> int:
    st.session_state["_id_counter"] = st.session_state.get("_id_counter", 0) + 1
    return st.session_state["_id_counter"]


def _ids_key(who: str, kind: str) -> str:
    return f"{who}_{kind}_ids"


def _field_key(who: str, kind: str, entry_id: int, field: str) -> str:
    return f"{who}_{kind}_{entry_id}_{field}"


def _fmt_date(d: date | None) -> str:
    return d.strftime("%m/%d/%Y") if d else ""


def _render_address_section(who: str, label: str) -> None:
    ids_key = _ids_key(who, "addr")
    st.session_state.setdefault(ids_key, [])

    st.markdown(f"**{label} — addresses**")
    for entry_id in list(st.session_state[ids_key]):
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            with c1:
                r1 = st.columns(3)
                r1[0].text_input("Street", key=_field_key(who, "addr", entry_id, "street_name"))
                r1[1].text_input("City", key=_field_key(who, "addr", entry_id, "city"))
                r1[2].text_input("State/Province", key=_field_key(who, "addr", entry_id, "state_province"))
                r2 = st.columns(3)
                r2[0].text_input("ZIP / postal code", key=_field_key(who, "addr", entry_id, "zip_code"))
                r2[1].text_input("Country", value="USA", key=_field_key(who, "addr", entry_id, "country"))
                r2[2].selectbox("Type", ADDRESS_TYPES, key=_field_key(who, "addr", entry_id, "address_type"))
                r3 = st.columns(3)
                r3[0].date_input("Moved in", key=_field_key(who, "addr", entry_id, "date_from"), value=None)
                present_key = _field_key(who, "addr", entry_id, "present")
                present = r3[2].checkbox("Currently lives here", key=present_key)
                if not present:
                    r3[1].date_input("Moved out", key=_field_key(who, "addr", entry_id, "date_to"), value=None)
            with c2:
                if st.button("Remove", key=f"remove_{who}_addr_{entry_id}"):
                    st.session_state[ids_key].remove(entry_id)
                    st.rerun()

    if st.button(f"+ Add {label.lower()} address", key=f"add_{who}_addr"):
        st.session_state[ids_key].append(_next_id())
        st.rerun()


def _render_employment_section(who: str, label: str) -> None:
    ids_key = _ids_key(who, "emp")
    st.session_state.setdefault(ids_key, [])

    st.markdown(f"**{label} — employment**")
    for entry_id in list(st.session_state[ids_key]):
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            with c1:
                r1 = st.columns(3)
                r1[0].text_input("Employer", key=_field_key(who, "emp", entry_id, "employer"))
                r1[1].text_input("Role", key=_field_key(who, "emp", entry_id, "role"))
                r1[2].selectbox("Type", EMPLOYMENT_TYPES, key=_field_key(who, "emp", entry_id, "employment_type"))
                r2 = st.columns(3)
                r2[0].date_input("Start date", key=_field_key(who, "emp", entry_id, "date_from"), value=None)
                present_key = _field_key(who, "emp", entry_id, "present")
                present = r2[2].checkbox("Current job", key=present_key)
                if not present:
                    r2[1].date_input("End date", key=_field_key(who, "emp", entry_id, "date_to"), value=None)
            with c2:
                if st.button("Remove", key=f"remove_{who}_emp_{entry_id}"):
                    st.session_state[ids_key].remove(entry_id)
                    st.rerun()

    if st.button(f"+ Add {label.lower()} job", key=f"add_{who}_emp"):
        st.session_state[ids_key].append(_next_id())
        st.rerun()


def _render_travel_section(who: str, label: str) -> None:
    ids_key = _ids_key(who, "trv")
    st.session_state.setdefault(ids_key, [])

    st.markdown(f"**{label} — international travel**")
    for entry_id in list(st.session_state[ids_key]):
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            with c1:
                r1 = st.columns(3)
                r1[0].selectbox("Entry or exit", TRAVEL_EVENT_TYPES, key=_field_key(who, "trv", entry_id, "event_type"))
                r1[1].date_input("Date", key=_field_key(who, "trv", entry_id, "date"), value=None)
                r1[2].text_input("Port / city", key=_field_key(who, "trv", entry_id, "port_or_city"))
                r2 = st.columns(3)
                r2[0].text_input("Status/class (e.g. B2)", key=_field_key(who, "trv", entry_id, "status_or_class"))
                r2[1].text_input("I-94 number (if known)", key=_field_key(who, "trv", entry_id, "i94_number"))
                r2[2].selectbox(
                    "Inspected/admitted?",
                    ["Unknown", "Yes", "No"],
                    key=_field_key(who, "trv", entry_id, "inspected"),
                )
            with c2:
                if st.button("Remove", key=f"remove_{who}_trv_{entry_id}"):
                    st.session_state[ids_key].remove(entry_id)
                    st.rerun()

    if st.button(f"+ Add {label.lower()} trip", key=f"add_{who}_trv"):
        st.session_state[ids_key].append(_next_id())
        st.rerun()


def _collect_addresses(who: str) -> list[dict]:
    out = []
    for entry_id in st.session_state.get(_ids_key(who, "addr"), []):
        street = st.session_state.get(_field_key(who, "addr", entry_id, "street_name"), "")
        if not street:
            continue
        present = st.session_state.get(_field_key(who, "addr", entry_id, "present"), False)
        out.append(
            {
                "street_name": street,
                "city": st.session_state.get(_field_key(who, "addr", entry_id, "city"), ""),
                "state_province": st.session_state.get(_field_key(who, "addr", entry_id, "state_province"), ""),
                "zip_code": st.session_state.get(_field_key(who, "addr", entry_id, "zip_code"), ""),
                "country": st.session_state.get(_field_key(who, "addr", entry_id, "country"), "USA"),
                "address_type": st.session_state.get(_field_key(who, "addr", entry_id, "address_type"), "lived"),
                "date_from": _fmt_date(st.session_state.get(_field_key(who, "addr", entry_id, "date_from"))),
                "date_to": "Present" if present else _fmt_date(st.session_state.get(_field_key(who, "addr", entry_id, "date_to"))),
            }
        )
    return out


def _collect_employment(who: str) -> list[dict]:
    out = []
    for entry_id in st.session_state.get(_ids_key(who, "emp"), []):
        employer = st.session_state.get(_field_key(who, "emp", entry_id, "employer"), "")
        if not employer:
            continue
        present = st.session_state.get(_field_key(who, "emp", entry_id, "present"), False)
        out.append(
            {
                "employer": employer,
                "role": st.session_state.get(_field_key(who, "emp", entry_id, "role"), ""),
                "employment_type": st.session_state.get(_field_key(who, "emp", entry_id, "employment_type"), "employed"),
                "date_from": _fmt_date(st.session_state.get(_field_key(who, "emp", entry_id, "date_from"))),
                "date_to": "Present" if present else _fmt_date(st.session_state.get(_field_key(who, "emp", entry_id, "date_to"))),
            }
        )
    return out


def _collect_travel(who: str) -> list[dict]:
    out = []
    for entry_id in st.session_state.get(_ids_key(who, "trv"), []):
        trip_date = st.session_state.get(_field_key(who, "trv", entry_id, "date"))
        if not trip_date:
            continue
        inspected_choice = st.session_state.get(_field_key(who, "trv", entry_id, "inspected"), "Unknown")
        entry = {
            "event_type": st.session_state.get(_field_key(who, "trv", entry_id, "event_type"), "entry"),
            "date": _fmt_date(trip_date),
            "port_or_city": st.session_state.get(_field_key(who, "trv", entry_id, "port_or_city"), ""),
            "status_or_class": st.session_state.get(_field_key(who, "trv", entry_id, "status_or_class"), ""),
        }
        i94 = st.session_state.get(_field_key(who, "trv", entry_id, "i94_number"), "")
        if i94:
            entry["i94_number"] = i94
        if inspected_choice != "Unknown":
            entry["inspected"] = inspected_choice == "Yes"
        out.append(entry)
    return out


def _render_case_builder() -> None:
    st.markdown("### Marriage details")
    m1, m2, m3, m4 = st.columns(4)
    m1.date_input("Marriage date", key="marriage_date", value=None)
    m2.text_input("City", key="marriage_city")
    m3.text_input("State/Province", key="marriage_state")
    m4.text_input("Country", value="USA", key="marriage_country")

    st.divider()
    st.markdown("## Beneficiary")
    _render_address_section("ben", "Beneficiary")
    _render_employment_section("ben", "Beneficiary")
    _render_travel_section("ben", "Beneficiary")

    st.divider()
    st.markdown("## Petitioner")
    _render_address_section("pet", "Petitioner")
    _render_employment_section("pet", "Petitioner")
    _render_travel_section("pet", "Petitioner")


def _build_case_from_form() -> dict:
    marriage_date = st.session_state.get("marriage_date")
    return {
        "beneficiary": {
            "addresses": _collect_addresses("ben"),
            "employment": _collect_employment("ben"),
            "travel": _collect_travel("ben"),
        },
        "petitioner": {
            "addresses": _collect_addresses("pet"),
            "employment": _collect_employment("pet"),
            "travel": _collect_travel("pet"),
        },
        "marriage": {
            "date": _fmt_date(marriage_date),
            "city": st.session_state.get("marriage_city", ""),
            "state": st.session_state.get("marriage_state", ""),
            "country": st.session_state.get("marriage_country", "USA"),
        },
    }


# ---------------------------------------------------------------------------
# Analysis + results rendering
# ---------------------------------------------------------------------------


def _run_analysis(raw: dict, validate_petitioner: bool) -> dict | None:
    try:
        return build_packet_from_json(raw, validate_petitioner=validate_petitioner)
    except Exception as exc:  # noqa: BLE001 - surface any pipeline error to the user
        st.error(f"Couldn't process this case: {exc}")
        return None


def main() -> None:
    st.set_page_config(page_title="AOS Timeline Builder", layout="wide")
    st.title("AOS Timeline Builder")
    st.caption(
        "Rules-based timeline and consistency review for marriage-based adjustment of status (I-485) cases. This tool flags data gaps and inconsistencies for staff review — it does not provide legal advice, predict case outcomes, or replace attorney/accredited representative judgment."
    )
    st.info(
        "Draft QC output. Attorney/accredited representative review required before relying on any flagged item.",
        icon="ℹ️",
    )

    if "case_json" not in st.session_state:
        st.session_state["case_json"] = ""

    mode = st.radio(
        "How do you want to enter case data?",
        ["Build a case", "Paste JSON"],
        horizontal=True,
    )

    validate_petitioner = True

    if mode == "Build a case":
        _render_case_builder()
        st.divider()
        validate_petitioner = st.checkbox("Also validate petitioner timeline", value=True, key="vp_form")
        run_clicked = st.button("Run analysis", type="primary")
        if run_clicked:
            raw = _build_case_from_form()
            packet = _run_analysis(raw, validate_petitioner)
            if packet is not None:
                st.session_state["packet"] = packet
    else:
        st.markdown("### Case JSON")
        if st.button("Load sample case"):
            st.session_state["case_json"] = json.dumps(SAMPLE_CASE, indent=2)

        uploaded = st.file_uploader("Upload case JSON", type=["json"])
        if uploaded is not None:
            st.session_state["case_json"] = uploaded.read().decode("utf-8")

        st.session_state["case_json"] = st.text_area(
            "Paste case JSON",
            value=st.session_state["case_json"],
            height=320,
        )

        validate_petitioner = st.checkbox("Also validate petitioner timeline", value=True, key="vp_json")
        run_clicked = st.button("Run analysis", type="primary")
        if run_clicked:
            try:
                raw = json.loads(st.session_state["case_json"])
            except json.JSONDecodeError as exc:
                st.error(f"That's not valid JSON: {exc}")
                raw = None
            if raw is not None:
                packet = _run_analysis(raw, validate_petitioner)
                if packet is not None:
                    st.session_state["packet"] = packet

    packet = st.session_state.get("packet")

    if not packet:
        st.info("Fill in case details above (or load the sample case), then press **Run analysis**.")
        return

    st.divider()

    tab_exec, tab_attorney, tab_email, tab_timelines = st.tabs(
        ["Executive Summary", "Attorney Detail", "Client Email", "Timelines"]
    )

    with tab_exec:
        _render_executive_summary(packet)

    with tab_attorney:
        _render_attorney_detail(packet)

    with tab_email:
        _render_client_email(packet)

    with tab_timelines:
        _render_timelines(packet)

    st.divider()
    _render_exports(packet)

    with st.expander("Raw packet JSON"):
        st.json(packet)


def _render_executive_summary(packet: dict) -> None:
    ex = packet.get("executive_summary", {}) or {}
    policy = ex.get("policy", {}) or {}

    disclaimer = ex.get("disclaimer")
    if disclaimer:
        st.caption(disclaimer)

    st.subheader(f"Policy: {policy.get('label', 'Default')}")

    posture = ex.get("overall_review_status")
    if posture:
        st.metric("Overall review status", str(posture).replace("_", " ").upper())

    st.markdown("### Flagged items")
    flagged_items = ex.get("flagged_items") or []
    if not flagged_items:
        st.write("No items flagged for this case.")
    for i, item in enumerate(flagged_items, start=1):
        severity = item.get("severity", "")
        badge = SEVERITY_BADGE.get(severity, "⚪")
        header = f"{badge} {i}. {item.get('topic')} ({item.get('role')}) — {severity} — {item.get('resolution_type')}"
        with st.expander(header):
            st.write(item.get("summary", ""))

    st.markdown("### Client follow-up")
    follow = ex.get("client_followup", {}) or {}
    col1, col2 = st.columns(2)
    col1.metric("Required (P0)", follow.get("required_p0", 0))
    col2.metric("Recommended (P1)", follow.get("recommended_p1", 0))
    blocking = follow.get("priority_topics") or []
    if blocking:
        st.warning("Priority topics: " + ", ".join(blocking))

    st.markdown("### Evidence planning")
    evidence_items = (ex.get("evidence_planning") or {}).get("items") or []
    if evidence_items:
        for e in evidence_items:
            st.write(f"- {e}")
    else:
        st.write("No additional evidence planning items.")


def _render_attorney_detail(packet: dict) -> None:
    st.markdown("### All flagged items")
    items = packet.get("flagged_items", {}).get("items", [])
    if not items:
        st.write("No flagged items generated.")
    for i, item in enumerate(items, start=1):
        severity = item.get("severity", "")
        badge = SEVERITY_BADGE.get(severity, "⚪")
        header = f"{badge} {i}. {item.get('topic')} — {severity} — score {item.get('score')}"
        with st.expander(header):
            narrative = (item.get("narrative") or {}).get("rendered_text")
            if narrative:
                st.text(narrative)

    st.markdown("### Full issue list")
    counts = packet.get("issues", {}).get("counts", {}) or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("High", counts.get("high", 0))
    c2.metric("Medium", counts.get("medium", 0))
    c3.metric("Low", counts.get("low", 0))
    c4.metric("Total", counts.get("total", 0))

    sev_filter = st.multiselect(
        "Filter by severity", ["high", "medium", "low"], default=["high", "medium", "low"]
    )
    by_severity = packet.get("issues", {}).get("by_severity", {}) or {}
    rows = [
        {
            "severity": sev,
            "category": issue.get("category"),
            "message": issue.get("message"),
            "ref_id": issue.get("ref_id"),
        }
        for sev in sev_filter
        for issue in by_severity.get(sev, [])
    ]
    if rows:
        st.dataframe(rows, use_container_width=True)
    else:
        st.write("No issues match the selected filters.")


def _render_client_email(packet: dict) -> None:
    ccp = packet.get("client_clarification_pack", {}) or {}
    email = ccp.get("email", {}) or {}
    summary = ccp.get("summary", {}) or {}

    st.markdown(f"**Subject:** {email.get('subject', '')}")
    st.text_area(
        "Email body (copy/paste ready)",
        value=email.get("body", ""),
        height=420,
    )
    by_priority = summary.get("by_priority", {}) or {}
    st.caption(
        f"{summary.get('total_questions', 0)} question(s) — "
        f"{by_priority.get('P0', 0)} required, "
        f"{by_priority.get('P1', 0)} recommended, "
        f"{by_priority.get('P2', 0)} optional"
    )


def _render_timelines(packet: dict) -> None:
    for who in ("beneficiary", "petitioner"):
        st.markdown(f"### {who.capitalize()}")
        timeline = packet.get("timelines", {}).get(who, {}) or {}

        st.write("Addresses")
        st.dataframe(timeline.get("addresses_lived", []), use_container_width=True)

        st.write("Employment")
        st.dataframe(timeline.get("employment", []), use_container_width=True)

        st.write("Travel")
        st.dataframe(timeline.get("travel", []), use_container_width=True)


def _render_exports(packet: dict) -> None:
    st.markdown("### Export")
    col1, col2 = st.columns(2)

    with col1:
        markdown = export_packet_markdown(packet)
        st.download_button(
            "Download Markdown",
            data=markdown,
            file_name="attorney_review_packet.md",
            mime="text/markdown",
        )

    with col2:
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                export_packet_pdf(packet, tmp_path)
                pdf_bytes = tmp_path.read_bytes()
            finally:
                # Case data can include sensitive PII (names, addresses, A-numbers) -
                # never leave the rendered PDF sitting on disk after we've read it.
                tmp_path.unlink(missing_ok=True)
            st.download_button(
                "Download PDF",
                data=pdf_bytes,
                file_name="attorney_review_packet.pdf",
                mime="application/pdf",
            )
        except ImportError:
            st.caption("Install `reportlab` to enable PDF export.")


if __name__ == "__main__":
    main()
