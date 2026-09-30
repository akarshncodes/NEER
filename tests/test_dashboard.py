"""Stage 5 test: the Control Room runs a whole case with button clicks (headless Streamlit)."""
import pytest
from streamlit.testing.v1 import AppTest

from neer import config


@pytest.mark.slow
def test_dashboard_runs_a_case():
    at = AppTest.from_file(str(config.ROOT / "neer/app/dashboard.py"), default_timeout=180).run()
    assert not at.exception
    at.sidebar.slider[0].set_value(0.0).run()
    [b for b in at.sidebar.button if "Start" in b.label][0].click().run()
    assert not at.exception
    assert any("Approve" in b.label for b in at.button)          # waiting for the human
    [b for b in at.sidebar.button if "Autopilot" in b.label][0].click().run()
    assert not at.exception
    assert any("CLOSED" in m.value and "FIXED" in m.value for m in at.markdown)


def test_badges_and_ai_stats():
    from neer.app import components as C
    ai = dict(agent="Skeptic", text="x", kind="decision", provider="groq:openai/gpt-oss-120b",
              numbers=dict(ai_choice="dismiss", rules_default="open_case", guard="vetoed: dismiss -> open_case"))
    fb = dict(agent="Orchestrator", text="y", kind="decision", provider="rules (after: groq: 429)",
              numbers=dict(ai_choice="acoustic_check", rules_default="acoustic_check", guard="accepted"))
    plain = dict(agent="Sentinel", text="z", kind="alert", provider=None, numbers={})
    assert C.brain_of(ai) == "AI: groq" and C.brain_of(fb) == "rules" and C.brain_of(plain) is None
    assert C.ai_stats([ai, fb, plain]) == (1, 1, 1)
    page = C.timeline_html([ai, fb, plain])
    assert "AI: groq" in page and "guard: vetoed" in page and "guard: accepted" in page and page.count("bdg ") == 4


# ------------------------------------------------------------------ operations map (no network: tiles load in the browser)
def _full_layers():
    import numpy as np
    from neer.app import opsmap
    from neer.sim.network import get_network
    net = get_network()
    z = net.zone_names[0]
    js = net.zone_junctions(z)
    post = np.random.default_rng(0).random(len(net.junctions))
    return opsmap.Layers(
        posterior=post, top_areas=[("A-1", js[:6]), ("A-2", js[6:11])], current=("A-1", js[:6]),
        quiet=[("A-3", js[12:16])], repaired=("A-4", js[17:21]), true_leaks=[js[0]], case_zone=z,
        sensor_drop={s: 0.1 * i for i, s in enumerate(net.sensors)}, masked=[net.sensors[0]], crew=True)


def test_to_latlon_covers_about_4km_by_3km_around_madurai():
    import numpy as np
    from neer.app import geo
    from neer.sim.network import get_network
    xy = np.array(list(get_network().coords.values()), dtype=float)
    ll = geo.to_latlon(xy)
    north_km = (ll[:, 0].max() - ll[:, 0].min()) * 111.32
    east_km = (ll[:, 1].max() - ll[:, 1].min()) * 111.32 * np.cos(np.radians(9.925))
    assert 2.5 < north_km <= 3.05 and 3.0 < east_km <= 4.05
    assert abs(ll[:, 0].mean() - 9.925) < 0.01 and abs(ll[:, 1].mean() - 78.12) < 0.01


@pytest.mark.parametrize("view", ["zone", "full"])
def test_both_map_modes_build(view):
    import plotly.graph_objects as go
    from neer.app import opsmap
    city = opsmap.build_map("city", _full_layers(), view, height=600)
    flat = opsmap.build_map("schematic", _full_layers(), view, height=600)
    assert city.layout.map.style == "open-street-map" and city.layout.height == 600
    assert all(isinstance(t, go.Scattermap) for t in city.data)
    assert all(isinstance(t, go.Scatter) for t in flat.data)
    for fig in (city, flat):
        assert any(t.marker.showscale for t in fig.data if t.marker is not None and t.marker.showscale)   # colour bar
        titles = [t.marker.colorbar.title.text for t in fig.data if t.marker is not None and t.marker.showscale]
        assert titles == ["Relative likelihood (not calibrated)"]
    assert "Network placement is illustrative" in city.layout.annotations[0].text
    assert opsmap.build_map("city").layout.map.zoom != opsmap.build_map("city", _full_layers(), "zone").layout.map.zoom


@pytest.mark.slow
def test_city_map_falls_back_to_schematic_when_tiles_unreachable(monkeypatch):
    from neer.app import geo
    monkeypatch.setattr(geo, "tiles_available", lambda *a, **k: False)
    at = AppTest.from_file(str(config.ROOT / "neer/app/dashboard.py"), default_timeout=180).run()
    at.sidebar.slider[0].set_value(0.0).run()
    [r for r in at.sidebar.radio if r.label == "Map"][0].set_value("city").run()      # schematic is the default
    [b for b in at.sidebar.button if "Start" in b.label][0].click().run()
    assert not at.exception
    assert any("unreachable" in c.value for c in at.caption)


# ------------------------------------------------------------------ flowchart, decision cards, ledger table
def test_flow_progress_and_figure():
    from neer.app import flowchart
    hist = [("__start__",), ("sentinel",), ("skeptic_gate",), ("detective",), ("orchestrator",), ("approve_plan",)]
    order, running = flowchart.progress(hist, "open")
    assert order == ["sentinel", "skeptic_gate", "detective", "orchestrator"] and running == ("approve_plan",)
    done, end = flowchart.progress(hist[:3] + [("auditor",), ()], "closed")
    assert end == ("closed",) and done[-1] == "auditor"
    fig = flowchart.flow_figure(order + ["field_commander", "orchestrator"], running)
    texts = " ".join(a["text"] for a in fig.layout.annotations)
    assert "WAITING FOR HUMAN" in texts and "×2" in texts
    for label in ("acoustic no → re-plan", "NOT FIXED → re-listen", "PARTLY FIXED → Detective"):
        assert label in texts                                                   # the labelled loop-backs are drawn


def test_decision_cards_and_refused_count():
    from neer.app import components as C
    ai = dict(agent="Skeptic", text="Dismissed?", kind="alert", provider="groq:openai/gpt-oss-120b (after: groq: 429)",
              numbers=dict(ai_choice="dismiss", rules_default="open_case", guard="vetoed: dismiss -> open_case",
                           cited=["t = 19.1 > 4.0"], rejected=2))
    plan = dict(agent="Orchestrator", text="Plan: acoustic_check in A-211.", kind="decision", provider="rules",
                numbers=dict(ai_choice="acoustic_check", rules_default="acoustic_check", guard="accepted", cited=[]))
    aud = dict(agent="Auditor", text="FIXED - proven in 3 h.", kind="verdict", provider=None, numbers={})
    refused = dict(agent="Field Commander", text="Dig refused: no approver", kind="alert", provider=None, numbers={})
    page = C.decision_cards([ai, plan, aud, refused])
    assert "AI: groq" in page and "dismiss → open_case (rule veto)" in page and "t = 19.1 &gt; 4.0" in page
    assert "fallbacks (1)" in page and "not run yet" in page and "FIXED" in page
    assert C.ai_stats([ai, plan, aud, refused]) == (1, 0, 1 + 2 + 1)       # veto + 2 refused answers + 1 refused dig


def test_ledger_table_has_chips():
    from neer.app import components as C
    rows = [dict(when="Day 8", dimension="Mass balance", finding="+19.8 L/s", supports="leak", reliability="high", source="get_zone_flow"),
            dict(when="", dimension="AI decision", finding="x", supports="vetoed by rule", reliability="m", source="groq"),
            dict(when="", dimension="Independent audit", finding="FIXED", supports="fixed", reliability="high", source="verify_repair")]
    page = C.ledger_html(rows)
    assert "chip-leak" in page and "chip-veto" in page and "chip-fixed" in page and "Source tool" in page


# ------------------------------------------------------------------ twin sandbox (what-if)
def test_sandbox_helper_returns_pressure_deltas_for_a_leak():
    from neer.app import sandbox
    from neer.sim.network import get_network
    net = get_network()
    r = sandbox.run_whatif(sandbox.build_event("leak", node="239", lps=20))
    assert set(r.junction_change_m) == set(net.junctions)                  # a pressure change for every junction
    assert min(r.junction_change_m.values()) < -0.2                         # a 20 L/s leak visibly lowers pressure
    assert sum(v < -0.2 for v in r.junction_change_m.values()) >= 20         # most junctions lose pressure
    assert sum(v < -0.2 for v in r.sensor_change_m.values()) >= 3
    assert r.zone_inflow_lps["Z5"] == pytest.approx(19.5, abs=1.0)          # and adds the leak flow to its zone
    assert "20 L/s leak" in r.sentence and "Z5's inflow" in r.sentence


def test_sandbox_pump_trip_changes_pressure_but_no_inflow():
    from neer.app import sandbox
    r = sandbox.run_whatif(sandbox.build_event("pump_trip"))
    assert r.active_hours[0] == 8 and min(r.junction_change_m.values()) < -1      # the tanks keep refilling after 13:00
    assert all(abs(v) < 0.5 for v in r.zone_inflow_lps.values())
    assert "changes no zone inflow" in r.sentence


def test_sandbox_map_overlay_builds_in_both_modes():
    from neer.app import opsmap, sandbox
    r = sandbox.run_whatif(sandbox.build_event("leak", node="239", lps=20))
    layers = opsmap.Layers(whatif_drop={j: -c for j, c in r.junction_change_m.items()}, whatif_at=("node", "239", "leak"))
    for mode in ("city", "schematic"):
        fig = opsmap.build_map(mode, layers, "full", selectable=True)
        assert any(t.name == "junction-select" for t in fig.data)
        assert any(t.marker is not None and t.marker.showscale and t.marker.colorbar.title.text == "Predicted pressure drop (m)"
                   for t in fig.data)


@pytest.mark.slow
def test_sandbox_tab_simulates_and_starts_a_case():
    at = AppTest.from_file(str(config.ROOT / "neer/app/dashboard.py"), default_timeout=180).run()
    assert not at.exception
    at.sidebar.slider[0].set_value(0.0).run()
    [b for b in at.button if b.label == "Simulate"][0].click().run()
    assert not at.exception
    assert any("leak at junction" in s.value for s in at.success)
    [b for b in at.button if b.label == "Run a case on this"][0].click().run()
    assert not at.exception
    assert at.session_state["scenario"] == "whatif"
    assert any("Approve" in b.label for b in at.button)                      # the injected leak opened a real case


# ------------------------------------------------------------------ operations board + case report
def _record(case_id="CASE-T1", verdict="FIXED", status="closed", llr=(-3.0, -5.0, -7.5), litres=1_728_000.0, quiet=2):
    from neer.app import board
    values = dict(case_id=case_id, scenario="leak_20", status=status, zone="Z5", leak_size_lps=20.0, visits=3, replans=2,
                  verdict=verdict, verdict_reason="Zone inflow back to normal: proven in 3 h.", contractor="released",
                  llr_trace=list(llr), last_event="start",
                  area_history=[dict(area="A-1", action="acoustic", result="no")] * quiet + [dict(area="A-2", action="dig", result="repaired")],
                  timeline=[dict(agent="Sentinel", text="Alarm ≈ +19.8 L/s → zone Z5 ✓", kind="alert", provider=None, numbers={}),
                            dict(agent="Orchestrator", text="Plan: acoustic_check in A-1.", kind="decision",
                                 provider="groq:openai/gpt-oss-120b (after: x)", numbers={})],
                  ledger=[dict(when="Day 8", dimension="Mass balance", finding="+19.8 L/s", supports="leak",
                               reliability="high", source="get_zone_flow")])
    return board.make_record(values, dict(litres_saved_per_day=litres, crew_hours=9.7, false_alarms_avoided=1), False, (), 7)


def test_board_columns_and_impact_strip():
    from neer import config
    from neer.app import board
    assert board.column_of("closed", False) == "Closed" and board.column_of("watch", False) == "Watch"
    assert board.column_of("open", True, ("approve_plan",)) == "Waiting for approval"
    assert board.column_of("escalated", False) == "Waiting for approval"
    assert board.column_of("open", False, ("field_commander",)) == "Field work"
    assert board.column_of("open", False, ("auditor",)) == "Verifying"
    assert board.column_of("open", False, ("detective",)) == "Investigating"
    recs = [_record("CASE-A"), _record("CASE-B", litres=864_000.0, quiet=1)]
    imp = board.impact(recs)
    assert imp["water_m3_per_day"] == pytest.approx(2592.0) and imp["crew_hours"] == pytest.approx(19.4)
    assert imp["wasted_digs_avoided"] == 3 and imp["false_alarms_avoided"] == 2
    assert imp["inr_per_day"] == pytest.approx(2592.0 * config.COST_PER_M3_INR)
    blocks = board.board_html(recs, active_id="CASE-A")
    assert len(blocks) == 6 and "CASE-A" in blocks[-1] and "FIXED" in blocks[-1] and "kactive" in blocks[-1]


def test_case_report_builds_a_non_empty_pdf_with_a_page_per_case():
    import re
    from neer.app import report
    recs = [_record("CASE-A"), _record("CASE-B", verdict=None, status="watch", llr=())]
    pdf = report.build_report(recs)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 5_000
    assert len(re.findall(rb"/Type /Page\b(?!s)", pdf)) == 2                      # short cases: exactly one page each
    assert report.auditor_chart([-3.0, -6.0, -8.0])[:8] == b"\x89PNG\r\n\x1a\n"
    assert report.LABEL == "Simulated city: not field data"
    with pytest.raises(ValueError):
        report.build_report([])


@pytest.mark.slow
def test_report_from_a_real_case_and_board_run_all():
    from neer.agents.runner import run_case
    from neer.app import board, report
    from neer.tools import world as W
    s = run_case("leak_20", 7)
    rec = board.make_record(s.model_dump(), W._world.kpi, False, (), 7)
    assert rec["column"] == "Closed" and rec["verdict"] == "FIXED" and rec["kpi"]["litres_saved_per_day"] > 0
    assert rec["quiet_surveys"] >= 0 and len(report.build_report([rec])) > 5_000

    at = AppTest.from_file(str(config.ROOT / "neer/app/dashboard.py"), default_timeout=300).run()
    at.sidebar.slider[0].set_value(0.0).run()
    [b for b in at.button if b.label == "Run all demo scenarios"][0].click().run()
    assert not at.exception
    cols = [m.value for m in at.markdown if 'class="kcol"' in m.value]
    assert len(cols) == 6
    by_name = {name: block for name, block in zip(board.COLUMNS, cols)}
    assert by_name["Watch"].count("kcard") == 1 and by_name["Closed"].count("kcard") >= 2
    assert all(any(f"{sc}" in c for c in cols) for sc in board.DEMO_SCENARIOS)


# ------------------------------------------------------------------ 3D city view (no browser)
def test_city3d_deck_builds_for_a_case():
    import json
    from neer.app import city3d
    layers = _full_layers()
    deck = city3d.build_deck(layers, city3d.Camera(pitch=50, bearing=-30), dark=False)
    spec = json.loads(deck.to_json())
    kinds = [lay["@@type"] for lay in spec["layers"]]
    for lay in spec["layers"]:                  # pydeck turns any string prop into an expression: only accessors may be one
        assert all(k.startswith("get") for k, val in lay.items() if isinstance(val, str) and val.startswith("@@="))
    assert {"PathLayer", "ColumnLayer", "ScatterplotLayer", "PolygonLayer", "TextLayer"} <= set(kinds)
    assert spec["initialViewState"]["pitch"] == 50 and spec["initialViewState"]["bearing"] == -30
    cols = next(lay for lay in spec["layers"] if lay["@@type"] == "ColumnLayer")["data"]
    top = max(cols, key=lambda r: r["h"])
    assert top["title"].startswith("Junction") and "Relative likelihood" in top["line1"] and "pressure drop" in top["line2"].lower()
    assert top["h"] > 3 * min(r["h"] for r in cols)                                  # suspected junctions stand out
    flown = city3d.build_deck(layers, city3d.Camera(fly_to=True), dark=True)
    assert flown.initial_view_state.pitch == 60 and flown.initial_view_state.zoom > deck.initial_view_state.zoom
    empty = city3d.build_deck(basemap=False)                                         # before any case: no crash
    assert empty.map_style is None


def test_blueprint_deck_builds():
    from neer.app import city3d
    d = city3d.build_blueprint()
    assert d.map_style is None and len(d.layers) >= 5
