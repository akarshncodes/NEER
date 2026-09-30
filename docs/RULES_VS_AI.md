# Rules vs AI: who decides what

NEER has two brains on purpose. The **rules/engine** brain is deterministic, tested code. The **AI** brain is an LLM chain
(Groq, then Gemini, then `rules`). The AI never produces a number a tool did not return, and a rule guard sits between every
AI answer and every consequence.

| Rules / engine own | AI owns |
|---|---|
| **Physics:** hydraulic simulation (WNTR), the digital twin's replay of pump trips, valve closures and planned work | **Evidence interpretation:** reading the hypothesis table and the localisation result in plain language (is the evidence concentrated or spread out? would more data help?) |
| **Statistics:** baseline, t-scores, pressure score, evidence dimensions, the Auditor's sequential test | **Hypothesis choice:** `most_likely` of leak / operation / planned_work / sensor_fault / temporary_demand |
| **Thresholds:** mass-balance t > 4.0, minimum actionable leak (6 L/s), wait budget, 8 visits / 6 re-plans per round | **Missing-evidence requests:** which extra check to run (`replay_operation`, `sensor_health`, `get_supply_calendar`, `get_pressure`, `wait_one_day`), or whether to `gather_more` at all |
| **Safety validator:** acoustic yes before a dig, named approver with role supervisor/engineer, one open dig per case, SCADA read-only, contractor released only on FIXED | **Where to search next:** `target_area` among the top-3 candidate surveys and the current area, weighing likelihood, information gain, crew-hours and value |
| **Tool validation:** typed inputs and outputs, timeouts, retries, circuit breaker, allowed-set and candidate checks on every AI answer | **Re-planning:** what to do after a quiet area, an empty dig, a NOT FIXED or PARTLY FIXED verdict |
| **Auditor verdict:** measures the pre-repair loss itself, 999:1 to close, never reads the crew report or the AI's reasoning | **Explanations:** the `reason` and cited evidence written into the timeline and the evidence ledger |
| **Rule veto:** the Skeptic may not `dismiss` when the engine verdict is `leak` and the zone t-score is above the threshold | *(The AI may always pick the more cautious option: `open_case`, `gather_more`, `escalate`.)* |

Every AI decision is logged (timeline entry and ledger row `AI decision`) with provider, choice, the choice `rules()` would
have made, the guard outcome and the evidence cited. The Control Room shows this as badges on each timeline entry.

## Worked example: `wrong_repair`, seed 41, chain brain

The crew fixes the wrong pipe first. This is a real run with the live chain from this project (scenario `wrong_repair`,
seed 41, `--llm chain`). Groq answered 12 of its 13 AI decisions; the rest were the rules default. Lines are quoted exactly as
the timeline stored them (provider and guard in brackets); this is an excerpt, lines in between are left out.

```
Skeptic | Most likely: leak. Could not explain it away: Mass‑balance shows excess flow 19.13 L/s, far above the 4.0 L/s threshold, with a raw excess of 19.67 L/s and no operation, work, sensor fault or demand pattern to explain it. Case opened.  [groq:openai/gpt-oss-120b; guard: accepted]
Detective | Zone Z5, leak ≈ 19.7 ± 0.7 L/s. Relative likelihood: A-255 26%, A-239 23%, A-213 20%. Evidence spread out: The leak (~19.7 L/s) is moderate, but the likelihood is split among three zones (26%, 23%, 20%), showing no clear concentration; an extra day could sharpen the map. Waiting one more day for data.  [groq:openai/gpt-oss-120b; guard: accepted]
Orchestrator | Plan: acoustic_check in A-255. All candidate areas have moderate likelihoods, with A-255 highest at 0.263, so an acoustic check is needed before any dig.  [groq:openai/gpt-oss-120b; guard: accepted]
Skeptic | Plan approved for the supervisor: The plan targets the most likely area (A-255 with relative likelihood 0.263) and includes an acoustic check before any dig, satisfying the safety-first requirement.  [groq:openai/gpt-oss-120b; guard: accepted]
Orchestrator | Re-plan: acoustic_check in A-239. The last acoustic check was negative in A-255; the next best candidate by value is A-239 (value 0.341).  [groq:openai/gpt-oss-120b; guard: accepted]
Field Commander | Acoustic loggers in A-239 overnight: LEAK NOISE HEARD.  [rules/tools]
Orchestrator | Plan: request_dig in A-239. Acoustic check was positive in A-239, so we can proceed to dig there.  [groq:openai/gpt-oss-120b; guard: accepted]
Auditor | NOT FIXED - [Z5, own meter reading] No real change: 19.6 -> 19.9 L/s extra after 2 h. The leak is still there. Contractor payment held. Case reopened.  [rules/tools]
Orchestrator | Re-plan: acoustic_check in A-213. A-213 offers the next highest chance of finding the leak (0.251) with reasonable information gain, and we have not yet surveyed it.  [groq:openai/gpt-oss-120b; guard: accepted]
Field Commander | Acoustic loggers in A-213 overnight: quiet - no dig.  [rules/tools]
```

What to notice:

- **Interpretation:** the Skeptic names `leak` as most likely and builds its reason from the tool's numbers (t = 19.13 against the 4.0 threshold), although it misreads that t-score as L/s (see the caveats).
- **Choice of where:** after the quiet survey in A-255 the Orchestrator moves to A-239 and cites its value (0.341); the next survey there hears leak noise.
- **Rules own the verdict:** the crew reports the leak repaired, yet the Auditor measures 19.6 -> 19.9 L/s and says NOT FIXED. The Auditor never saw the AI's reasoning and the AI cannot overrule it.
- **Re-planning:** the Orchestrator then surveys three other areas, returns to A-239 (now with the highest likelihood, 0.526), and the second repair is proven FIXED.
- **Caveats, seen in the same run:** the model sometimes muddles units or words (it called the t-score "excess flow ... L/s" and called areas "zones"). Nothing it wrote fed back into a calculation, but the prose needs review. On the Detective's first look it asked for one more day where the rules default was `proceed`; the guard allowed it (a wait is cautious), at the cost of a day.

## If I remove the LLM, does NEER still work?

**Yes.** Numbers from `docs/EVAL.md` and `docs/LLM_EVAL.md` (seeds 41-45, 16 scenarios, 80 runs each):

| Brain | Passed | Closed while a leak still ran | Actions without a valid approver/role |
|---|---|---|---|
| `rules` only (no keys) | 79/80 | 0 | 0 |
| `chain` (LLM first, `rules` last) | 79/80 | 0 | 0 |

- The one failing run is the same in both: `two_leaks` seed 43 escalates to a human after 8 visits. It fails safely.
- **What this does not show.** In that `chain` run the free-tier quotas were exhausted, so only 13 of 337 decisions were answered by a live model and 324 fell back to `rules` (see the warning at the top of `docs/LLM_EVAL.md`). It proves the fallback path works and that the safety counters hold there. It does not show that the live AI improves or harms outcomes, and the pass rate gives no evidence that it does.
- **What the AI adds today** is not a higher pass rate but readable reasoning (hypotheses, cited evidence, where and why), and a second opinion that the guards can veto. In an earlier run of the same code (103 live answers), eight Skeptic answers dismissed a real leak; the rule veto overrode all of them and those cases still closed FIXED. That is the reason the guard lives in code and not in the prompt.
- To measure the live AI properly, re-run `NEER_LLM_MIN_INTERVAL_S=6 uv run python -m neer.eval.llm_eval --seeds 41,42,43,44,45` when quota is available.
