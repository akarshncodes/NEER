"""Pre-demo self-check (about 30 s). Run on the demo laptop before judges arrive:

    uv run python scripts/selfcheck.py

Checks every piece the demo uses and prints PASS / FAIL with a hint.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
results = []


def check(name: str, fn, hint: str = "") -> None:
    t0 = time.time()
    try:
        detail = fn() or ""
        results.append(True)
        print(f"  PASS  {name}  {detail}  ({time.time() - t0:.1f}s)")
    except Exception as e:  # noqa: BLE001
        results.append(False)
        print(f"  FAIL  {name}: {type(e).__name__}: {str(e)[:160]}" + (f"\n        hint: {hint}" if hint else ""))


def libraries():
    import fastapi, langgraph, mcp, plotly, pydeck, streamlit, wntr  # noqa: F401,E401
    return f"streamlit {streamlit.__version__}, wntr {wntr.__version__}"


def dataset():
    man = ROOT / "dataset" / "MANIFEST.csv"
    assert man.exists(), "dataset/MANIFEST.csv missing"
    return f"{sum(1 for _ in open(man)) - 1} files"


def scripted_case():
    from neer.agents.runner import run_case
    s = run_case("leak_20", 7)
    assert s.status == "closed" and s.verdict == "FIXED", (s.status, s.verdict)
    return f"leak_20 -> {s.verdict}, {s.visits} visits"


def night_watch():
    from neer.live import NightWatch
    nw = NightWatch.start(7)
    e1, e2 = nw.run_night(), nw.run_night()
    assert e1["outcome"] == "clean" and e2["outcome"] == "case", (e1["outcome"], e2["outcome"])
    cid = e2["case_id"]
    nw.decide(cid, True, "Selfcheck", "supervisor")
    v = nw.cases[cid].state()
    assert v.get("verdict") == "FIXED", v.get("verdict")
    return f"night 2 opened {cid} -> FIXED"


def safety():
    from neer.agents.runner import run_case
    from neer.tools import world as W
    s = run_case("leak_20", 7, approver="Visitor", approver_role="viewer")
    assert s.status == "escalated" and W._world.kpi["digs"] == 0
    return "viewer refused, escalated"


def database_and_api():
    from fastapi.testclient import TestClient
    from neer.api.server import app
    api = TestClient(app)
    assert api.get("/api/health").json()["status"] == "ok"
    cid = api.post("/api/cases", json={"scenario": "pump_trip", "seed": 7}).json()["case_id"]
    assert api.get(f"/api/cases/{cid}").json()["status"] == "watch"
    assert api.get("/api/dataset/network/junctions.csv?limit=1").json()["total_rows"] == 92
    return "health, POST case, GET case, dataset"


def ai_keys():
    from neer import config  # noqa: F401  (loads .env)
    keys = [k for k in ("GROQ_API_KEY", "GOOGLE_API_KEY") if os.getenv(k)]
    return f"keys found: {', '.join(keys) or 'none - Ask NEER will use the rules explainer'}"


def live_ai():
    if not os.getenv("GROQ_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        return "skipped (no keys)"
    from neer.agents.explain import ask
    from neer.agents.runner import run_case
    ans, who = ask("Is the leak really fixed?", run_case("leak_20", 7).model_dump(), brain="chain")
    return f"answered by {who}"


def maps():
    from neer.app import city3d, opsmap
    opsmap.build_map("schematic", opsmap.Layers(), "full")
    city3d.build_blueprint()
    from neer.app import geo
    return "schematic + 3D OK; street tiles " + ("reachable" if geo.tiles_available() else "NOT reachable (use Schematic)")


if __name__ == "__main__":
    os.environ.setdefault("NEER_LLM_CHAIN", "rules")
    from neer import config
    config.use_private_runtime("selfcheck")
    print("NEER self-check")
    check("Python libraries", libraries, "run: uv sync")
    check("Demo dataset", dataset, "run: uv run python scripts/build_dataset.py")
    check("Agents: hidden leak case", scripted_case)
    check("Night watch: opens a case by itself and proves FIXED", night_watch)
    check("Safety: a viewer cannot dig", safety)
    check("Database + REST API", database_and_api)
    check("AI keys (.env)", ai_keys)
    os.environ.pop("NEER_LLM_CHAIN", None)
    from importlib import reload
    reload(config)
    check("Live AI answer (Groq/Gemini)", live_ai, "check internet / quota; the demo still works on rules")
    check("Maps", maps)
    ok = sum(results)
    print(f"\n{ok}/{len(results)} checks passed" + ("  - ready to demo" if ok == len(results) else ""))
    sys.exit(0 if ok == len(results) else 1)
