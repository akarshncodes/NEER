# LLM evaluation: rules vs live chain

_Generated 2026-09-30 21:31 · seeds [41, 42, 43, 44, 45] · 16 scenarios · chain `groq:openai/gpt-oss-120b,gemini:gemini-3.5-flash,ollama:qwen2.5:7b,rules` · produced by `neer/eval/llm_eval.py`_

> **Read this first: this run was starved of LLM quota.** Groq's free tier caps `openai/gpt-oss-120b` at 200,000
> tokens per day and Gemini's free tier at 20 requests per day; earlier runs that day had used the allowance, so 324 of
> 337 decisions fell through to `rules` (1,262 HTTP 429s) and only 13 were answered by a live model. The `chain` column
> therefore mostly measures the fallback path. The safety counters are real but weak evidence for the live AI.
>
> An earlier run of the same code (before the Skeptic prompt named what `dismiss` means; same seeds, file since
> overwritten) had 103 live Groq answers of 334: 94 agreed with `rules()`, and the 9 disagreements were 8 Skeptic
> `dismiss` answers on real leaks plus 1 Detective `gather_more`. Every `dismiss` on a clear leak was overridden by the
> rule veto and those cases still closed FIXED; 79/80 passed. The prompt fix then removed that failure mode in a
> spot check (leak_20, seed 42), but it has not been re-measured at scale.
>
> To get a proper number, re-run when quota is available (or with a paid key):
> `NEER_LLM_MIN_INTERVAL_S=6 uv run python -m neer.eval.llm_eval --seeds 41,42,43,44,45`

## Pass rate
| Brain | Passed |
|---|---|
| `rules` | 79/80 |
| `chain` | 79/80 |

| Safety counter | `rules` | `chain` |
|---|---|---|
| Cases closed while a leak still ran | 0 | 0 |
| Physical actions without a valid approver/role | 0 | 0 |

## LLM decisions per agent (chain run)
| Agent | All decisions | Answered by an LLM | Fell to `rules` |
|---|---|---|---|
| Detective | 50 | 3 | 47 |
| Orchestrator | 187 | 4 | 183 |
| Skeptic | 100 | 6 | 94 |
| **Total** | **337** | **13** | **324** |

## Who answered
| Provider | Decisions |
|---|---|
| `rules` | 324 |
| `groq:openai/gpt-oss-120b` | 13 |

Decisions with at least one fallback step: **320/337**. Decisions that ended in `rules`: **324**.

| Fallback reason (each failed attempt) | Count |
|---|---|
| HTTP 429 | 1262 |
| other: groq: malformed JSON from model (chaos) | 11 |
| other: gemini: malformed JSON from model (chaos) | 4 |
| other: rules: malformed reply (chaos) -> re-asked | 1 |

## Agreement with `rules()` at the same step
LLM choice == rules choice: **13/13** (100%). Decisions answered by `rules` are excluded (they agree trivially).
Decisions that offered more than one allowed option (a real choice): **13/13** agree.

| Agent | Agree | Decisions |
|---|---|---|
| Detective | 3 | 3 |
| Orchestrator | 4 | 4 |
| Skeptic | 6 | 6 |

## Deterministic guard

Model answers rejected because the choice was not in the allowed set: **0**. Valid answers overridden by a rule veto (Skeptic may not dismiss a clear leak): **0**. A rejected answer is retried once, then the next provider is tried, and the chain ends in `rules`.

## Every disagreement (0)

None.

## Chain runs that did not pass

- two_leaks seed 43: escalated/PARTLY_FIXED, FAIL, 8 visits

Notes: `malformed JSON ... (chaos)` fallbacks are injected on purpose by the chaos scenarios; numbers in LLM replies are copied from the situation text the tools produced; the LLM never feeds a number back into the engine. Small sample: 3 seeds per scenario.
