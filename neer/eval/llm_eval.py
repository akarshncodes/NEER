"""LLM evaluation: run every scenario with the `rules` brain and with the live LLM chain, then compare.

    uv run python -m neer.eval.llm_eval --seeds 41,42,43

Writes docs/LLM_EVAL.md (docs/EVAL.md is left alone). Numbers come only from the runs below.
"""
from __future__ import annotations

import argparse
import os
import re
from collections import Counter, defaultdict
from datetime import datetime

from neer import config
from neer.agents import llm as L
from neer.agents.runner import run_case
from neer.eval.run_eval import passed
from neer.sim.scenarios import SCENARIOS
from neer.tools import world as W


def run_all(brain: str, seeds: list[int]) -> list[dict]:
    """One row per (scenario, seed): outcome plus every decision the agents made."""
    rows = []
    for name, sc in SCENARIOS.items():
        for seed in seeds:
            L.clear_decision_log()
            s = run_case(name, seed, llm=brain)
            wld = W._world
            wrong = s.status == "closed" and len(wld.city.truth()) > 0            # closed while a leak still runs
            unsafe = sum(1 for wo in wld.work_orders.values() if wo.action in ("dig", "repair")
                         and (not wo.approved_by or (wo.approver_role or "") not in config.APPROVER_ROLES))
            rows.append(dict(scenario=name, seed=seed, ok=passed(sc.expect, s), status=s.status,
                             wrong_close=wrong, unsafe=unsafe,
                             verdict=s.verdict or "-", visits=s.visits, decisions=list(L.DECISION_LOG)))
            print(f"{brain:5} {'PASS' if rows[-1]['ok'] else 'FAIL'} {name:15} seed {seed} {s.status} {s.verdict or '-'}")
    return rows


def _why(fail: str) -> str:
    """Bucket a fallback message into a short reason."""
    m = re.search(r"\b(4\d\d|5\d\d)\b", fail)
    if "timeout" in fail:
        return "timeout"
    if "not in allowed set" in fail:
        return "guard: choice not in allowed set"
    if m:
        return f"HTTP {m.group(1)}"
    return "other: " + fail[:60]


def report(rules_rows: list[dict], chain_rows: list[dict], seeds: list[int]) -> str:
    n = len(rules_rows)
    decs = [(r, d) for r in chain_rows for d in r["decisions"]]
    llm_decs = [(r, d) for r, d in decs if d.provider != "rules"]
    per_agent = Counter(d.agent for _, d in decs)
    llm_agent = Counter(d.agent for _, d in llm_decs)
    prov = Counter(d.provider for _, d in decs)
    fb = Counter(_why(f) for _, d in decs for f in d.fallbacks)
    fb_decisions = sum(1 for _, d in decs if d.fallbacks)
    rules_final = sum(1 for _, d in decs if d.provider == "rules")
    rejected = sum(d.guard_rejections for _, d in decs)
    vetoes = sum(d.vetoed for _, d in decs)
    agree = [(r, d) for r, d in llm_decs if d.choice == d.rules_choice]
    dis = [(r, d) for r, d in llm_decs if d.choice != d.rules_choice]
    multi = [(r, d) for r, d in llm_decs if len(d.allowed) > 1]
    multi_agree = sum(d.choice == d.rules_choice for _, d in multi)
    agree_by = defaultdict(lambda: [0, 0])
    for _, d in llm_decs:
        agree_by[d.agent][1] += 1
        agree_by[d.agent][0] += d.choice == d.rules_choice

    def end(r: dict) -> str:
        return f"{r['status']}/{r['verdict']}, {'pass' if r['ok'] else 'FAIL'}"

    out = [
        "# LLM evaluation: rules vs live chain",
        "",
        f"_Generated {datetime.now():%Y-%m-%d %H:%M} · seeds {seeds} · {len(SCENARIOS)} scenarios · "
        f"chain `{os.getenv('NEER_LLM_CHAIN', config.LLM_CHAIN)}` · produced by `neer/eval/llm_eval.py`_",
        "",
        "## Pass rate",
        "| Brain | Passed |", "|---|---|",
        f"| `rules` | {sum(r['ok'] for r in rules_rows)}/{n} |",
        f"| `chain` | {sum(r['ok'] for r in chain_rows)}/{n} |",
        "",
        "| Safety counter | `rules` | `chain` |", "|---|---|---|",
        f"| Cases closed while a leak still ran | {sum(r['wrong_close'] for r in rules_rows)} | "
        f"{sum(r['wrong_close'] for r in chain_rows)} |",
        f"| Physical actions without a valid approver/role | {sum(r['unsafe'] for r in rules_rows)} | "
        f"{sum(r['unsafe'] for r in chain_rows)} |",
        "",
        "## LLM decisions per agent (chain run)",
        "| Agent | All decisions | Answered by an LLM | Fell to `rules` |", "|---|---|---|---|",
    ]
    for a, c in sorted(per_agent.items()):
        out.append(f"| {a} | {c} | {llm_agent[a]} | {c - llm_agent[a]} |")
    out += [f"| **Total** | **{len(decs)}** | **{len(llm_decs)}** | **{rules_final}** |", "",
            "## Who answered",
            "| Provider | Decisions |", "|---|---|"]
    out += [f"| `{p}` | {c} |" for p, c in prov.most_common()]
    out += ["", f"Decisions with at least one fallback step: **{fb_decisions}/{len(decs)}**. "
                f"Decisions that ended in `rules`: **{rules_final}**.", ""]
    if fb:
        out += ["| Fallback reason (each failed attempt) | Count |", "|---|---|"]
        out += [f"| {k} | {c} |" for k, c in fb.most_common()]
    else:
        out.append("No fallbacks happened.")
    out += ["", f"## Agreement with `rules()` at the same step",
            f"LLM choice == rules choice: **{len(agree)}/{len(llm_decs)}**"
            f" ({len(agree) / max(len(llm_decs), 1):.0%}). Decisions answered by `rules` are excluded (they agree trivially).",
            f"Decisions that offered more than one allowed option (a real choice): **{multi_agree}/{len(multi)}** agree.",
            "", "| Agent | Agree | Decisions |", "|---|---|---|"]
    out += [f"| {a} | {v[0]} | {v[1]} |" for a, v in sorted(agree_by.items())]
    out += ["", "## Deterministic guard", "",
            f"Model answers rejected because the choice was not in the allowed set: **{rejected}**. "
            f"Valid answers overridden by a rule veto (Skeptic may not dismiss a clear leak): **{vetoes}**. "
            "A rejected answer is retried once, then the next provider is tried, and the chain ends in `rules`.",
            "", f"## Every disagreement ({len(dis)})", ""]
    if dis:
        out += ["| Scenario (seed) | Agent | LLM choice | Rules choice | Veto | LLM reason | Case ended |",
                "|---|---|---|---|---|---|---|"]
        for r, d in dis:
            reason = d.reason.replace("|", "/").replace("\n", " ")
            out.append(f"| {r['scenario']} ({r['seed']}) | {d.agent} | `{d.choice}` | `{d.rules_choice}` | "
                       f"{'yes' if d.vetoed else '-'} | {reason} | {end(r)} |")
    else:
        out.append("None.")
    failed = [r for r in chain_rows if not r["ok"]]
    out += ["", "## Chain runs that did not pass", ""]
    out += [f"- {r['scenario']} seed {r['seed']}: {end(r)}, {r['visits']} visits" for r in failed] or ["None."]
    out += ["", "Notes: `malformed JSON ... (chaos)` fallbacks are injected on purpose by the chaos scenarios; numbers in LLM replies are copied from the situation text the tools produced; "
                "the LLM never feeds a number back into the engine. Small sample: 3 seeds per scenario."]
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="41,42,43")
    a = ap.parse_args()
    seeds = [int(x) for x in a.seeds.split(",")]
    chain_env = os.environ.get("NEER_LLM_CHAIN", config.LLM_CHAIN)
    rules_rows = run_all("rules", seeds)
    os.environ["NEER_LLM_CHAIN"] = chain_env              # start_case("rules") overwrote it
    chain_rows = run_all("chain", seeds)
    out = config.ROOT / "docs" / "LLM_EVAL.md"
    out.write_text(report(rules_rows, chain_rows, seeds))
    print(f"\nrules {sum(r['ok'] for r in rules_rows)}/{len(rules_rows)}  chain {sum(r['ok'] for r in chain_rows)}/"
          f"{len(chain_rows)}  ->  {out}")


if __name__ == "__main__":
    main()
