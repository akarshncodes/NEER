"""Operations board: every case of this session as a card in a Kanban column, plus the impact strip.

Pure functions (no Streamlit) so they can be tested. A case record is a plain dict kept in `st.session_state`,
because each new case replaces the simulated world: the record keeps what the report and the board need.
"""
from __future__ import annotations

import html
from typing import Optional

from neer import config

COLUMNS = ["Watch", "Investigating", "Waiting for approval", "Field work", "Verifying", "Closed"]
DEMO_SCENARIOS = ["pump_trip", "leak_20", "wrong_repair", "two_leaks"]
_KPI_KEYS = ("litres_saved_per_day", "crew_hours", "wasted_digs", "false_alarms_avoided", "digs", "acoustic_checks")


def column_of(status: str, pending: bool, next_nodes: tuple = (), last_event: str = "", verdict: Optional[str] = None) -> str:
    """Which Kanban column a case belongs in right now."""
    if status == "closed":
        return "Closed"
    if status in ("watch", "no_alarm"):
        return "Watch"
    if status == "escalated" or pending:
        return "Waiting for approval"
    node = next_nodes[0] if next_nodes else ""
    if node == "field_commander":
        return "Field work"
    if node == "auditor" or (last_event == "repaired" and not verdict):
        return "Verifying"
    return "Investigating"


def make_record(values: dict, kpi: dict, pending: bool, next_nodes: tuple = (), seed: Optional[int] = None) -> dict:
    """Snapshot one case (graph state values + the world's KPIs) into a record for the board and the report."""
    history = values.get("area_history", []) or []
    return dict(
        case_id=values["case_id"], scenario=values.get("scenario", ""), seed=seed, status=values.get("status", ""),
        zone=values.get("zone"), leak_size_lps=float(values.get("leak_size_lps") or 0.0),
        visits=int(values.get("visits") or 0), replans=int(values.get("replans") or 0),
        verdict=values.get("verdict"), verdict_reason=values.get("verdict_reason", ""),
        contractor=values.get("contractor"), tier=values.get("tier", ""),
        column=column_of(values.get("status", ""), pending, tuple(next_nodes), values.get("last_event", ""),
                         values.get("verdict")),
        kpi={k: kpi.get(k, 0) for k in _KPI_KEYS},
        quiet_surveys=sum(1 for h in history if h.get("action") == "acoustic" and h.get("result") == "no"),
        timeline=list(values.get("timeline", [])), ledger=list(values.get("ledger", [])),
        llr_trace=[float(x) for x in values.get("llr_trace", []) or []])


def impact(records: list[dict]) -> dict:
    """The impact strip, summed over the cases of this session (each case ran in its own simulated world)."""
    water_m3 = sum(r["kpi"]["litres_saved_per_day"] for r in records) / 1000
    return dict(water_m3_per_day=water_m3,
                crew_hours=sum(r["kpi"]["crew_hours"] for r in records),
                wasted_digs_avoided=sum(r["quiet_surveys"] for r in records),
                false_alarms_avoided=int(sum(r["kpi"]["false_alarms_avoided"] for r in records)),
                inr_per_day=water_m3 * config.COST_PER_M3_INR)


def verdict_chip(r: dict) -> tuple[str, str]:
    """(label, css class) for the verdict chip on a card."""
    if r["verdict"] == "FIXED":
        return "FIXED", "vc-fixed"
    if r["verdict"] in ("NOT_FIXED", "PARTLY_FIXED"):
        return r["verdict"].replace("_", " "), "vc-bad"
    if r["status"] == "escalated":
        return "ESCALATED", "vc-bad"
    if r["status"] in ("watch", "no_alarm"):
        return "DISMISSED" if r["status"] == "watch" else "NO ALARM", "vc-none"
    return "OPEN", "vc-open"


def card_html(r: dict, active: bool = False) -> str:
    label, cls = verdict_chip(r)
    size = f"{r['leak_size_lps']:.1f} L/s" if r["leak_size_lps"] else "-"
    contractor = f' · contractor {html.escape(str(r["contractor"]))}' if r.get("contractor") else ""
    return (f'<div class="kcard{" kactive" if active else ""}"><div class="kid">{html.escape(r["case_id"])} '
            f'<span class="vchip {cls}">{html.escape(label)}</span></div>'
            f'<div class="kmeta">{html.escape(r["scenario"])} · zone {html.escape(str(r["zone"] or "-"))}</div>'
            f'<div class="kmeta">leak {size} · {r["visits"]} visit{"s" if r["visits"] != 1 else ""}{contractor}</div></div>')


def board_html(records: list[dict], active_id: Optional[str] = None) -> list[str]:
    """One HTML block per column (header with count, then the cards)."""
    out = []
    for name in COLUMNS:
        cards = [r for r in records if r["column"] == name]
        body = "".join(card_html(r, r["case_id"] == active_id) for r in cards) or '<div class="kempty">no cases</div>'
        out.append(f'<div class="kcol"><div class="khead">{name} <span class="kcount">{len(cards)}</span></div>{body}</div>')
    return out


# ------------------------------------------------------------------ the Streamlit tab
def render_tab(run_all, active_id: Optional[str]) -> None:
    """The "Operations board" tab. `run_all()` runs the demo scenarios on autopilot and fills `session_state.case_log`."""
    import streamlit as st
    from neer.app import report
    ss = st.session_state
    records = list(ss.get("case_log", {}).values())
    imp = impact(records)
    tiles = [("Water saved per day", f"{imp['water_m3_per_day']:,.0f} m³"), ("Crew-hours", f"{imp['crew_hours']:.1f}"),
             ("Wasted digs avoided", f"{imp['wasted_digs_avoided']}"), ("False alarms avoided", f"{imp['false_alarms_avoided']}"),
             (f"Money saved per day · at ₹{config.COST_PER_M3_INR}/m³ (assumption)", f"₹{imp['inr_per_day']:,.0f}")]
    from neer.app.components import kpi_strip
    st.markdown(kpi_strip(tiles, highlight=4, wide=(4,)), unsafe_allow_html=True)
    st.caption(f"Sums over the {len(records)} case(s) run in this session, in the simulated city. Money uses an assumed "
               f"₹{config.COST_PER_M3_INR} per m³ (config.COST_PER_M3_INR), not a measured tariff. "
               "\"Wasted digs avoided\" counts quiet acoustic surveys: areas cleared by listening instead of digging.")
    b1, b2, b3, _ = st.columns([1.2, 0.8, 1.4, 1.6])
    if b1.button("Run all demo scenarios", type="primary", width="stretch",
                 help="pump_trip, leak_20, wrong_repair and two_leaks on autopilot, one after another "
                      "(seed, tools and reasoning mode from the sidebar)."):
        run_all()
    if b2.button("Clear board", width="stretch", disabled=not records):
        ss.case_log = {}
        st.rerun()
    if records:
        key = tuple((r["case_id"], r["status"], len(r["timeline"]), r["verdict"]) for r in records)
        if ss.get("_pdf_key") != key:
            ss._pdf, ss._pdf_key = report.build_report(records), key
        b3.download_button("Download case report (PDF)", ss._pdf, file_name="neer_case_report.pdf",
                           mime="application/pdf", width="stretch")
    else:
        b3.button("Download case report (PDF)", disabled=True, width="stretch")
        st.info("No cases yet. Start one from the sidebar, or press **Run all demo scenarios**.")
    for col, block in zip(st.columns(len(COLUMNS)), board_html(records, active_id)):
        col.markdown(block, unsafe_allow_html=True)
