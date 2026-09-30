# Ready prompts for Claude Code (open Claude Code in the NEER/ folder)

The core build is done and tested. Use these prompts for improvements. Paste one prompt at a time.

---
## 1 · Turn on the real LLM chain and check it
Read CLAUDE.md and neer/agents/llm.py. I have put GROQ_API_KEY (and GOOGLE_API_KEY) in .env.
1. Run `uv run python -m neer.agents.runner --scenario leak_20 --llm chain` and `--scenario pump_trip --llm chain`.
2. Confirm the timeline shows the real provider (not only "rules"), and that decisions stay inside the allowed sets.
3. If a model returns invalid structured output, improve the prompts in neer/agents/prompts.py (keep them short). Do not relax the allowed-set validation.
4. Run `uv run python -m neer.eval.run_eval --seeds 21,22,23 --llm chain`, then report the pass rate, the LLM calls and the fallbacks.

Do not change engine numbers. Keep all tests green.

---
## 2 · Dashboard polish for the final demo
Read CLAUDE.md and neer/app/. Improve the Control Room without changing the agent logic:
- Zoom the map to the case zone after the Detective runs, with a "full city" toggle.
- Add a small "LLM decisions" counter (provider, fallbacks) under the KPI strip.
- Make the timeline auto-scroll to the newest entry.
- Keep `uv run pytest -q tests/test_dashboard.py` green, and take a screenshot to check the layout at 1600×1000.

---
## 3 · Explain-my-part cheat sheets
For each folder (neer/sim, neer/engine, neer/tools + neer/mcp_servers, neer/agents, neer/app + neer/eval), write docs/explain/<part>.md. Each sheet should give, in simple English:
- what it does, in 5 lines
- the 3 most important functions
- one likely judge question with its answer
- how to demo it in 30 seconds

Max 1 page each. Do not change code.
