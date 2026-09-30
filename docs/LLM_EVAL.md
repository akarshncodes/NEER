# LLM evaluation: rules vs live chain

_Generated 2026-09-30 21:04 · seeds [41, 42, 43] · 16 scenarios · chain `groq:openai/gpt-oss-120b,gemini:gemini-3.5-flash,ollama:qwen2.5:7b,rules` · produced by `neer/eval/llm_eval.py`_

## Pass rate
| Brain | Passed |
|---|---|
| `rules` | 47/48 |
| `chain` | 47/48 |

Wrongly closed cases are guarded by the Auditor (not the LLM); see `docs/EVAL.md` for safety counters.

## LLM decisions per agent (chain run)
| Agent | All decisions | Answered by an LLM | Fell to `rules` |
|---|---|---|---|
| Orchestrator | 113 | 46 | 67 |
| Skeptic | 60 | 36 | 24 |
| **Total** | **173** | **82** | **91** |

## Who answered
| Provider | Decisions |
|---|---|
| `rules` | 91 |
| `groq:openai/gpt-oss-120b` | 82 |

Decisions with at least one fallback step: **102/173**. Decisions that ended in `rules`: **91**.

| Fallback reason (each failed attempt) | Count |
|---|---|
| HTTP 429 | 369 |
| other: groq: malformed JSON from model (chaos) | 6 |

## Agreement with `rules()` at the same step
LLM choice == rules choice: **82/82** (100%). Decisions answered by `rules` are excluded (they agree trivially).
Decisions that offered more than one allowed option (a real choice): **63/63** agree.

| Agent | Agree | Decisions |
|---|---|---|
| Orchestrator | 46 | 46 |
| Skeptic | 36 | 36 |

## Deterministic guard

Model answers rejected because the choice was not in the allowed set: **0**. A rejected answer is retried once, then the next provider is tried, and the chain ends in `rules`.

## Every disagreement (0)

None.

## Chain runs that did not pass

- two_leaks seed 43: escalated/PARTLY_FIXED, FAIL, 8 visits

Notes: `malformed JSON ... (chaos)` fallbacks are injected on purpose by the chaos scenarios; numbers in LLM replies are copied from the situation text the tools produced; the LLM never feeds a number back into the engine. Small sample: 3 seeds per scenario.
