# Prompts: make the AI real, prove it, explain it
Open Claude Code in the `NEER/` folder and paste one prompt at a time. Finish each one (tests green, committed) before starting the next.

Before prompt A, get two free API keys and put them in `NEER/.env` (copy `.env.example` first):
- `GROQ_API_KEY` from console.groq.com
- `GOOGLE_API_KEY` from aistudio.google.com

---
## Prompt A: run the real AI chain and measure it (do this before the 10 PM review)

Read CLAUDE.md, neer/agents/llm.py and neer/agents/nodes.py. GROQ_API_KEY and GOOGLE_API_KEY are now in .env.

1. Run `uv run python -m neer.agents.runner --scenario leak_20 --llm chain` and `--scenario pump_trip --llm chain`. Confirm the timeline shows the real provider (groq or gemini), not only "rules". If structured output fails, fix the prompts in neer/agents/prompts.py (keep them short). Never loosen the allowed-set check.
2. Add a `--llm` option to neer/eval/run_eval.py if it isn't there. Run the evaluation on seeds 41,42,43 twice, once with `--llm rules` and once with `--llm chain`.
3. Write docs/LLM_EVAL.md with:
   - pass rate for rules vs chain
   - number of LLM decisions per agent
   - how often each provider answered, and how many fallbacks happened and why
   - agreement rate between the LLM's choice and what `rules()` would have chosen at the same step (log both at every decision)
   - a list of every disagreement: scenario, agent, LLM choice, rules choice, the LLM's reason, and how the case ended
   - how many LLM choices the deterministic guard rejected
4. Add one fast test that uses a fake LLM provider (no network) returning an invalid choice. Check that it falls through to the next provider and ends in `rules`.

Do not change engine code or engine numbers. Keep `uv run pytest -q` green. Commit as `stage8/llm: live chain run + LLM_EVAL.md`.

---
## Prompt B: give the AI the investigative decisions, and keep the rules as a safety veto

Read CLAUDE.md, docs/SPEC.md section 4, neer/agents/nodes.py, llm.py and prompts.py.

Goal: a clear split between the two brains.
- **Rules / engine own:** physics, calculations, thresholds, safety gates, tool validation, the final verification (Auditor).
- **The AI owns:** interpreting evidence, choosing between competing hypotheses, deciding what evidence is missing, choosing the next investigation and where, explaining why, and re-planning.

Change only neer/agents/ (and tests / docs). Keep the engine and tools untouched.

1. **Skeptic gate becomes a hypothesis judge.**
   - Build a list of competing explanations with the engine evidence for each: `leak`, `operation` (pump/valve), `planned_work`, `sensor_fault`, `temporary_demand` (e.g. fire draw).
   - The LLM returns a structured answer:
     - `most_likely`: one of the hypotheses
     - `missing_evidence`: zero or more of `["replay_operation", "sensor_health", "get_supply_calendar", "get_pressure", "wait_one_day"]`
     - `decision`: one of `["open_case", "dismiss", "gather_more"]`
     - `reason`
   - If it asks for missing evidence, run those tool calls (at most 2 extra rounds, then it must decide) and ask again with the new results.
   - **Guard (rules veto):** the LLM may not `dismiss` when the engine verdict is `leak` and the zone t-score is above the mass-balance threshold. It may always choose the more cautious option (`open_case` or `gather_more`). Record every veto in the timeline and in the evidence ledger (`dimension = "AI decision"`, `supports = "vetoed by rule"`).
2. **Orchestrator chooses WHERE, not only WHAT.**
   - Give the LLM the top 3 candidate surveys with likelihood, information gain, crew-hours and action value, plus the case history (areas already surveyed and their results).
   - It returns `action` from the allowed set, `target_area` (must be one of the candidates or the current area), and `reason`.
   - **Guard:** the target must be in the candidate list. `request_dig` is allowed only after an acoustic "yes" in that area (the safety validator already enforces this; also check it here). If the chosen area's action value is below 50% of the best candidate's, record `guard: low-value choice accepted` in the timeline so it is visible (don't block it).
3. **Detective adds an interpretation step.**
   - After `locate_leak`, the LLM gets the area likelihoods, the leak size ± uncertainty and the sensor-health result.
   - It writes a short interpretation: is the evidence concentrated or spread out, and is more data likely to help? It chooses `["proceed", "gather_more"]`.
   - `gather_more` routes to `wait_day` once at most (use the existing waits budget). Numbers only from tools.
4. **Every AI decision leaves a trace** in the timeline and the ledger with: provider, choice, rules-default choice, whether the guard accepted it, and the evidence it cited.
5. **The rules brain stays the last link** of the chain and answers every new question, so NEER still runs with no keys.
6. **Tests:** use a fake LLM provider (no network) and check that:
   - the guard vetoes a `dismiss` on a real leak
   - a different valid `target_area` from the LLM is used
   - an invalid area falls back to rules
   - `gather_more` runs the requested tool and then decides
7. Re-run `uv run python -m neer.eval.run_eval --seeds 41,42,43,44,45` with `--llm rules` and `--llm chain`, and update docs/EVAL.md and docs/LLM_EVAL.md. The 0 wrong closures and 0 unsafe actions must still hold in both. If they don't, fix the guard, not the numbers.
8. Update docs/SPEC.md section 4 (the agents table: "LLM decides" / "Deterministic guard").

Keep `uv run pytest -q` green. Commit as `stage8/agents: AI owns investigation, rules own safety`.

---
## Prompt C: make the split visible to judges

Read CLAUDE.md, neer/app/ and docs/LLM_EVAL.md.

1. Write docs/RULES_VS_AI.md with a two-column responsibility table:
   - rules/engine: physics, statistics, thresholds, safety validator, tool validation, Auditor verdict
   - AI: evidence interpretation, hypothesis choice, missing-evidence requests, where to search next, re-planning, explanations
   Add one worked example taken from a real chain run, with the timeline lines quoted exactly. End with the answer to "If I remove the LLM, does NEER still work?", using the numbers in docs/LLM_EVAL.md.
2. In the Control Room:
   - show a small badge on each timeline entry: `AI: groq` / `AI: gemini` / `rules`, plus `guard: accepted` or `guard: vetoed`
   - add a KPI tile: "AI decisions / fallbacks / vetoes"
   - add a sidebar note saying which brain is running
3. Keep tests/test_dashboard.py green. Take a screenshot at 1600×1000 and check that the badges are readable.

Commit as `stage8/app: rules-vs-AI badges`.
