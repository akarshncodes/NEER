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
