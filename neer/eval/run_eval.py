"""Evaluation: run every scripted scenario end to end and score the agents.

    uv run python -m neer.eval.run_eval                 # rules brain, 3 seeds, in-process tools
    uv run python -m neer.eval.run_eval --llm chain     # with the LLM chain (needs API keys)
    uv run python -m neer.eval.run_eval --mode mcp      # through the 4 MCP servers

Writes docs/EVAL.md. These are the ONLY agent-level numbers we quote.
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime

from neer import config
from neer.agents.runner import run_case
from neer.sim.scenarios import SCENARIOS
from neer.tools import world as W
from neer.tools.resilience import read_trace


def passed(expect: str, s) -> bool:
    if expect == "closed_fixed":
        return s.status == "closed" and s.verdict == "FIXED"
    if expect == "watch_or_no_alarm":
        return s.status in ("watch", "no_alarm") and s.visits == 0
    if expect == "no_alarm":
        return s.status == "no_alarm"
    return False


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(float(sorted(xs)[len(xs) // 2]), 1) if xs else "-"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="7,8,9")
    ap.add_argument("--llm", choices=["rules", "chain"], default="rules")
    ap.add_argument("--mode", choices=["direct", "mcp"], default="direct")
    a = ap.parse_args()
    config.use_private_runtime("eval")          # never share chaos/trace files with a running dashboard
    seeds = [int(x) for x in a.seeds.split(",")]

    rows, total, ok = [], 0, 0
    for name, sc in SCENARIOS.items():
        for seed in seeds:
            t0 = time.time()
            s = run_case(name, seed, mode=a.mode, llm=a.llm)
            secs = time.time() - t0
            trace = read_trace(2000)
            tools = [r for r in trace if not r["tool"].startswith("llm:") and r["agent"] != "mcp-server"]
            llm = [r for r in trace if r["tool"].startswith("llm:")]
            good = passed(sc.expect, s)
            wld = W.load() if a.mode == "mcp" else W._world
            wrong_close = s.status == "closed" and len(wld.city.truth()) > 0      # closed while a leak still runs
            digs = [wo for wo in wld.work_orders.values() if wo.action in ("dig", "repair")]
            unsafe = sum(1 for wo in digs if not wo.approved_by or (wo.approver_role or "") not in config.APPROVER_ROLES)
            invalid = sum(1 for r in tools if not r["ok"] and "invalid" in r["summary"].lower())
            days_to_fix = (wld.city.day - wld.case_start_day) if s.status == "closed" else None
            total += 1
            ok += good
            texts = " ".join(e["text"] for e in s.timeline)
            rows.append(dict(scenario=name, seed=seed, expect=sc.expect, status=s.status, verdict=s.verdict or "-",
                             visits=s.visits, replans=s.replans, tools=len(tools),
                             tool_errors=sum(1 for r in tools if not r["ok"]), llm=len(llm), secs=round(secs, 1),
                             notfixed="NOT FIXED" in texts, partly="PARTLY FIXED" in texts, ok=good,
                             wrong_close=wrong_close, escalated=s.status == "escalated",
                             crew_hours=wld.kpi.get("crew_hours", 0.0), unsafe=unsafe, invalid=invalid,
                             days_to_fix=days_to_fix, ledger=len(s.ledger)))
            print(f"{'PASS' if good else 'FAIL'}  {name:15} seed {seed}  {s.status:9} {s.verdict or '-':12} "
                  f"visits {s.visits}  tools {len(tools)}  {secs:.1f}s")

    by = {}
    for r in rows:
        by.setdefault(r["scenario"], []).append(r)
    lines = [
        "# NEER agent evaluation",
        "",
        f"_Generated {datetime.now():%Y-%m-%d %H:%M} · brain: **{a.llm}** · tools: **{a.mode}** · seeds {seeds}_",
        "",
        f"## Result: **passed {ok}/{total}** runs ({len(SCENARIOS)} scenarios × {len(seeds)} seeds)",
        "",
        "Simulated city (EPA Net3, harsh noise). A run passes when the case ends in the expected state:",
        "real leaks → CLOSED + FIXED (proven by the Auditor); look-alikes → WATCH / no alarm with **zero** field visits.",
        "",
        "| Scenario | What happens | Expected | Passed | Avg visits | Avg crew-h | Avg tool calls | Tool errors recovered | Avg time |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, rs in by.items():
        n = len(rs)
        lines.append(f"| `{name}` | {SCENARIOS[name].title} | {SCENARIOS[name].expect} | {sum(r['ok'] for r in rs)}/{n} | "
                     f"{sum(r['visits'] for r in rs) / n:.1f} | {sum(r['crew_hours'] for r in rs) / n:.1f} | "
                     f"{sum(r['tools'] for r in rs) / n:.0f} | "
                     f"{sum(r['tool_errors'] for r in rs)} | {sum(r['secs'] for r in rs) / n:.1f} s |")
    leak_rows = [r for r in rows if SCENARIOS[r["scenario"]].expect == "closed_fixed"]
    look_rows = [r for r in rows if SCENARIOS[r["scenario"]].expect != "closed_fixed"]
    lines += [
        "",
        "## Highlights",
        f"- Cases wrongly closed while a leak was still running: **{sum(r['wrong_close'] for r in rows)}/{total}**.",
        f"- Safety: physical actions without a valid approver/role: **{sum(r['unsafe'] for r in rows)}**; "
        f"invalid tool calls: **{sum(r['invalid'] for r in rows)}** of {sum(r['tools'] for r in rows)}.",
        f"- Time to verified repair (simulated days from first anomaly to FIXED): median "
        f"**{_median([r['days_to_fix'] for r in leak_rows if r['days_to_fix'] is not None])} days**; "
        f"crew-hours per leak case: median **{_median([r['crew_hours'] for r in leak_rows])} h**.",
        f"- Every case carries an evidence ledger (source tool, finding, direction, reliability): "
        f"median {_median([r['ledger'] for r in rows if r['status'] != 'no_alarm'])} rows per case.",
        f"- Runs that did not pass ended safely (escalated to a human or on watch): "
        f"**{sum((not r['ok']) and (r['escalated'] or r['status'] in ('watch', 'no_alarm')) for r in rows)}"
        f"/{total - ok}**.",
        f"- Leak cases closed with proof: **{sum(r['ok'] for r in leak_rows)}/{len(leak_rows)}**, "
        f"average {sum(r['visits'] for r in leak_rows) / max(len(leak_rows), 1):.1f} acoustic visits per case.",
        f"- Look-alike events that sent a crew: **{sum(r['visits'] > 0 for r in look_rows)}/{len(look_rows)}**.",
        f"- Wrong repairs caught by the Auditor (NOT FIXED, contractor held, re-planned): "
        f"**{sum(r['notfixed'] for r in rows if r['scenario'] == 'wrong_repair')}/{len(by.get('wrong_repair', []))}**.",
        f"- Second leaks found after PARTLY FIXED: **{sum(r['partly'] and r['ok'] for r in rows if r['scenario'] == 'two_leaks')}"
        f"/{len(by.get('two_leaks', []))}**.",
        f"- Chaos runs (SCADA timeout, broken LLM JSON, dead sensor, crew hears nothing) that still closed FIXED: "
        f"**{sum(r['ok'] for r in rows if r['scenario'].startswith('chaos'))}/{sum(1 for r in rows if r['scenario'].startswith('chaos'))}**.",
        "",
        "Engine-level accuracy (detection, localisation, Auditor) is in `scripts/engine_report.py`.",
    ]
    out = config.ROOT / "docs" / "EVAL.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"\npassed {ok}/{total}  ->  {out}")


if __name__ == "__main__":
    main()
