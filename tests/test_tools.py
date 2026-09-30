"""Stage 3 tests: the 19 tools, the resilience layer, chaos toggles and the MCP servers."""
import asyncio
import json

from neer.tools import chaos
from neer.tools.registry import ALL_TOOLS as T
from neer.tools.registry import SERVERS
from neer.tools.resilience import breaker, is_error, read_trace, resilient_tool
from neer.tools.world import World, set_world


def _start(scenario="leak_20", seed=7):
    set_world(World.new(scenario, seed))


def _find_and_dig(case="C1", approver="Asha", role="supervisor"):
    """Search like the agents will: acoustic first, dig only on yes."""
    loc = T["locate_leak"](case_id=case)
    for _ in range(8):
        area = T["plan_search_areas"](case_id=case, n=1)[0]
        if T["acoustic_check"](case_id=case, area_id=area["area_id"])["result"] == "yes":
            wo = T["create_work_order"](case_id=case, area_id=area["area_id"], action="dig", approved_by=approver,
                                        approver_role=role)
            st = T["crew_status"](work_order_id=wo["work_order_id"])
            if st["result"] == "repaired":
                return loc, wo
    return loc, None


def test_nineteen_tools():
    assert len(T) == 19 and sum(len(v) for v in SERVERS.values()) == 19


def test_leak_case_end_to_end():
    _start()
    zf = T["get_zone_flow"]()
    assert zf["detection"]["alarm"] and zf["detection"]["tier"] in ("PROBABLE", "CONFIRMED")
    assert T["replay_operation"]()["verdict"] == "leak"
    loc, wo = _find_and_dig()
    assert loc["zone"] == "Z5" and wo is not None
    v = T["verify_repair"](case_id="C1")
    assert v["verdict"] == "FIXED"
    assert T["release_contractor"](work_order_id=wo["work_order_id"])["decision"] == "released"
    k = T["kpi_report"]()
    assert k["repairs_verified"] == 1 and k["litres_saved_per_day"] > 1_000_000


def test_wrong_repair_is_caught_and_contractor_held():
    _start("wrong_repair")
    _, wo = _find_and_dig()
    v = T["verify_repair"](case_id="C1")
    assert v["verdict"] == "NOT_FIXED"
    assert T["release_contractor"](work_order_id=wo["work_order_id"])["decision"] == "held"


def test_pump_trip_is_explained():
    _start("pump_trip")
    assert T["get_ops_log"]()[0]["kind"] == "pump_trip"
    assert T["replay_operation"]()["verdict"] in ("operation", "no_alarm")


def test_dig_guards_and_idempotency():
    _start()
    T["locate_leak"](case_id="C1")
    area = T["plan_search_areas"](case_id="C1", n=1)[0]["area_id"]
    r = T["create_work_order"](case_id="C1", area_id=area, action="dig", approved_by="sup", approver_role="supervisor")
    assert is_error(r) and r["code"] == "refused"             # no acoustic yes yet
    a = T["create_work_order"](case_id="C1", area_id=area, action="acoustic")
    b = T["create_work_order"](case_id="C1", area_id=area, action="acoustic")
    assert a["work_order_id"] == b["work_order_id"]


def test_invalid_inputs_return_tool_errors():
    _start()
    for bad in (T["get_zone_flow"](days=99), T["get_zone_flow"](zone="Z9"), T["get_pressure"](sensors=["nope"]),
                T["plan_search_areas"](case_id="missing"), T["crew_status"](work_order_id="WO-999")):
        assert is_error(bad) and bad["code"] == "invalid_input"


def test_chaos_scada_timeout_recovers_by_retry():
    _start()
    chaos.set_toggle("scada_timeout", 2)
    out = T["get_zone_flow"]()
    assert not is_error(out)
    assert sum(1 for t in read_trace() if "timeout" in t["summary"]) == 2


def test_breaker_opens_after_repeated_failures():
    calls = {"n": 0}

    @resilient_tool("flaky", retries=0)
    def flaky() -> dict:
        calls["n"] += 1
        raise RuntimeError("down")

    for _ in range(3):
        assert flaky()["code"] == "internal"
    assert flaky()["code"] == "degraded" and calls["n"] == 3
    breaker.reset()


def test_chaos_sensor_dies_and_crew_finds_nothing():
    _start()
    chaos.set_toggle("sensor_dies", "241")
    health = {s["sensor"]: s["status"] for s in T["sensor_health"]()["sensors"]}
    assert health["241"] == "offline"
    loc = T["locate_leak"](case_id="C1")
    assert any("241" in e for e in loc["evidence"])
    chaos.set_toggle("crew_finds_nothing", 1)
    area = T["plan_search_areas"](case_id="C1", n=1)[0]["area_id"]
    assert T["acoustic_check"](case_id="C1", area_id=area)["result"] == "no"


def test_mcp_servers_list_19_tools():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from neer.mcp_servers.client import connections
    _start()

    async def count():
        n = 0
        for c in connections().values():
            p = StdioServerParameters(command=c["command"], args=c["args"], env=c["env"], cwd=c["cwd"])
            async with stdio_client(p) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    n += len((await s.list_tools()).tools)
                    if "scada" in c["args"][1]:
                        res = await s.call_tool("get_zone_flow", {"days": 1})
                        assert json.loads(res.content[0].text)["detection"]["alarm"]
        return n

    assert asyncio.run(count()) == 19


def test_role_based_approval_is_enforced():
    _start()
    T["locate_leak"](case_id="C1")
    from neer.tools.world import session
    with session() as w:                       # pretend the acoustic survey said yes in the top area
        area = T["plan_search_areas"](case_id="C1", n=1)[0]["area_id"]
        w.cases["C1"].acoustic_yes.add(area)
    for role in ("viewer", "field crew", None):
        r = T["create_work_order"](case_id="C1", area_id=area, action="dig", approved_by="Ravi", approver_role=role)
        assert is_error(r) and r["code"] == "refused"
    ok = T["create_work_order"](case_id="C1", area_id=area, action="dig", approved_by="Ravi", approver_role="engineer")
    assert ok["approver_role"] == "engineer"
    again = T["create_work_order"](case_id="C1", area_id=area, action="dig", approved_by="Ravi", approver_role="engineer")
    assert again["work_order_id"] == ok["work_order_id"]        # idempotent while open
    assert any(t["tool"] == "safety_validator" and "REFUSED" in t["summary"] for t in read_trace())


def test_auditor_ignores_the_detectives_conclusion():
    """Even if the Detective's zone and size are wrong, the Auditor measures the loss itself."""
    _start()
    _, wo = _find_and_dig()
    from neer.tools.world import session
    with session() as w:
        c = w.cases["C1"]
        c.zone_idx, c.pre_excess = 0, 0.0      # corrupt what the Detective said
    v = T["verify_repair"](case_id="C1")
    assert v["verdict"] == "FIXED" and v["pre_excess_lps"] > 10 and "Z5" in v["reason"]
