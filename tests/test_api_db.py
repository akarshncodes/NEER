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
