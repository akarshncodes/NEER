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
    [b for b in at.sidebar.button if "Start" in b.label][0].click().run()
    assert not at.exception
    assert any("unreachable" in c.value for c in at.caption)
