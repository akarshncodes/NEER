"""The case database (neer/store.py) and the REST API (neer/api/server.py)."""
import pytest
from fastapi.testclient import TestClient

from neer import store
from neer.agents.runner import run_case
from neer.api.server import app


def test_a_case_is_stored_in_every_table():
    s = run_case("wrong_repair", 41)
    c = store.get_case(s.case_id)
    assert c["status"] == "closed" and c["verdict"] == "FIXED" and c["scenario"] == "wrong_repair"
    assert len(c["timeline"]) == len(s.timeline) and len(c["ledger"]) == len(s.ledger)
    assert [a["gate"] for a in c["approvals"]][0] == "plan" and all(a["approved"] for a in c["approvals"])
    digs = [w for w in c["work_orders"] if w["action"] == "dig"]
    assert digs and all(w["approved_by"] and w["approver_role"] == "supervisor" for w in digs)
    assert all(w["status"] == "done" for w in c["work_orders"])


def test_refused_dig_is_recorded():
    s = run_case("leak_20", 7, approver="Visitor", approver_role="viewer")
    c = store.get_case(s.case_id)
    assert c["status"] == "escalated"
    assert not [w for w in c["work_orders"] if w["action"] == "dig"]          # the validator never created one


def test_sql_box_is_read_only():
    run_case("pump_trip", 7)
    assert store.query_readonly("SELECT scenario, status FROM cases")[0]["status"] == "watch"
    for bad in ("DELETE FROM cases", "SELECT 1; DROP TABLE cases", "UPDATE cases SET status='x'"):
        with pytest.raises(Exception):
            store.query_readonly(bad)
    assert store.counts()["cases"] == 1


def test_rest_api_end_to_end():
    api = TestClient(app)
    assert api.get("/api/health").json()["status"] == "ok"
    assert len(api.get("/api/scenarios").json()) == 16
    assert sum(len(v) for v in api.get("/api/tools").json().values()) == 19
    r = api.post("/api/cases", json={"scenario": "leak_20", "seed": 7})
    assert r.status_code == 200 and r.json()["verdict"] == "FIXED"
    cid = r.json()["case_id"]
    assert cid in [c["case_id"] for c in api.get("/api/cases").json()]
    detail = api.get(f"/api/cases/{cid}").json()
    assert detail["timeline"] and detail["ledger"] and detail["approvals"]
    assert api.get("/api/kpi").json()["fixed"] == 1
    assert api.get("/api/trace?limit=5").json()
    assert api.get("/api/cases/NOPE").status_code == 404
    assert api.post("/api/cases", json={"scenario": "nope"}).status_code == 404
    assert api.post("/api/cases", json={"scenario": "leak_20", "approver_role": "admin"}).status_code == 422


def test_dataset_api_and_ask_neer():
    api = TestClient(app)
    man = api.get("/api/dataset").json()
    assert any(f["file"] == "live_city/night_scan_0200_0400.csv" for f in man["files"])
    rows = api.get("/api/dataset/network/junctions.csv?limit=5").json()
    assert rows["total_rows"] == 92 and len(rows["rows"]) == 5
    assert api.get("/api/dataset/../pyproject.toml").status_code == 404          # no escaping the dataset folder
    cid = api.post("/api/cases", json={"scenario": "leak_20", "seed": 7}).json()["case_id"]
    a = api.post(f"/api/cases/{cid}/ask", json={"question": "Is the leak really fixed?", "brain": "rules"}).json()
    assert "999:1" in a["a"] and a["who"].startswith("rules")


def test_ask_neer_uses_only_the_case_record():
    from neer.agents.explain import ask, case_record
    s = run_case("leak_20", 7)
    v = s.model_dump()
    assert "Z5" in case_record(v)
    ans, who = ask("Why this search area?", v, brain="rules")
    assert who.startswith("rules") and v["areas"][0]["area_id"] in ans
