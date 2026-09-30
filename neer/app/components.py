"""Building blocks for the NEER Control Room (figures + small HTML pieces)."""
from __future__ import annotations

import html
from typing import Optional

import numpy as np
import plotly.graph_objects as go

from neer import config

ZONE_COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
AGENT_COLOURS = {"Sentinel": "#0e8fa3", "Skeptic": "#c73636", "Detective": "#2a78d6", "Orchestrator": "#1d3f8a",
                 "Field Commander": "#8a3fb0", "Auditor": "#1a8a3c", "Supervisor": "#b87800"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e8e7e2"


def _layout(fig: go.Figure, height: int, title: str = "") -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=36 if title else 8, b=8), paper_bgcolor="white",
                      plot_bgcolor="white", title=dict(text=title, font=dict(size=14, color=INK), x=0.01),
                      font=dict(family="Inter, sans-serif", size=12, color=INK2), showlegend=True,
                      legend=dict(orientation="h", y=-0.02, x=0, font=dict(size=11)))
    return fig


# ------------------------------------------------------------------ zone water bill
def water_bill(days_inflow: list[np.ndarray], normal: np.ndarray, sd: np.ndarray, zone: str,
               day_labels: list[str], height: int = 260) -> go.Figure:
    """Extra water entering the zone each hour (inflow minus normal) vs the normal wobble band (±2 sd)."""
    fig = go.Figure()
    n = len(days_inflow)
    x = np.arange(n * config.HOURS)
    extra = np.concatenate([d - normal for d in days_inflow])
    band = np.tile(2 * sd, n)
    fig.add_trace(go.Scatter(x=np.r_[x, x[::-1]], y=np.r_[band, -band[::-1]], fill="toself",
                             fillcolor="rgba(42,120,214,0.12)", line=dict(width=0), name="Normal wobble (±2 sd)",
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=extra, mode="lines", line=dict(color="#1d5aa6", width=2),
                             name="Extra water (L/s)"))
    for i in range(n):
        fig.add_vline(x=i * config.HOURS - 0.5, line=dict(color=GRID, width=1))
    fig.update_xaxes(tickvals=[i * config.HOURS + 12 for i in range(n)], ticktext=day_labels, gridcolor=GRID)
    fig.update_yaxes(title="L/s above normal", gridcolor=GRID, zeroline=True, zerolinecolor="#8f8e87")
    return _layout(fig, height, f"Zone {zone}: water nobody paid for")


# ------------------------------------------------------------------ auditor meter
def auditor_meter(llr: list[float], height: int = 220) -> go.Figure:
    thr = float(np.log(config.SPRT_ODDS))
    thr_fixed = float(np.log(config.SPRT_ODDS_FIXED))
    fig = go.Figure()
    fig.add_hrect(y0=thr, y1=max(thr * 1.6, max(llr + [0]) + 1), fillcolor="rgba(199,54,54,0.08)", line_width=0)
    fig.add_hrect(y0=min(-thr_fixed * 1.3, min(llr + [0]) - 1), y1=-thr_fixed, fillcolor="rgba(26,138,60,0.10)",
                  line_width=0)
    fig.add_trace(go.Scatter(x=list(range(1, len(llr) + 1)), y=llr, mode="lines+markers",
                             line=dict(color=INK, width=2), marker=dict(size=5), name="Evidence"))
    fig.add_hline(y=thr, line=dict(color="#c73636", dash="dash"), annotation_text="leak still there (99:1)",
                  annotation_position="top left")
    fig.add_hline(y=-thr_fixed, line=dict(color="#1a8a3c", dash="dash"), annotation_text="FIXED (999:1)",
                  annotation_position="bottom left")
    fig.update_xaxes(title="hours after repair", gridcolor=GRID)
    fig.update_yaxes(title="evidence", gridcolor=GRID, zeroline=True, zerolinecolor="#c9c8c2")
    fig.update_layout(showlegend=False)
    return _layout(fig, height, "Auditor: hour-by-hour proof")


# ------------------------------------------------------------------ HTML bits
def brain_of(entry: dict) -> str | None:
    """Which brain produced an AI-decision timeline entry: 'AI: groq', 'AI: gemini', 'AI: <name>' or 'rules'.
    None for entries that are not decisions (tool results, human gates)."""
    if "guard" not in (entry.get("numbers") or {}):
        return None
    prov = (entry.get("provider") or "rules").split(" ")[0].split(":")[0]
    return "rules" if prov == "rules" else f"AI: {prov}"


def ai_stats(entries: list[dict]) -> tuple[int, int, int]:
    """(decisions answered by a live model, fallbacks to rules after the chain failed, refused by safety rules).

    "Refused" = AI answers the guard rejected (outside the allowed set / failed a check) + rule vetoes
    + digs the safety validator refused."""
    ai = fb = veto = 0
    for e in entries:
        if e.get("agent") == "Field Commander" and str(e.get("text", "")).startswith("Dig refused"):
            veto += 1
        brain = brain_of(e)
        if brain is None:
            continue
        veto += int(e["numbers"].get("rejected", 0) or 0)
        if brain != "rules":
            ai += 1
        elif "(after:" in (e.get("provider") or ""):
            fb += 1
        veto += str(e["numbers"]["guard"]).startswith("vetoed")
    return ai, fb, veto


def _badges(e: dict) -> str:
    brain = brain_of(e)
    if brain is None:
        return ""
    guard = str(e["numbers"]["guard"])
    vetoed = guard.startswith("vetoed")
    tip = html.escape(f"AI chose '{e['numbers'].get('ai_choice')}'; rules default '{e['numbers'].get('rules_default')}'; "
                      f"guard: {guard}")
    return (f'<div class="bd" title="{tip}"><span class="bdg {"rules" if brain == "rules" else "ai"}">{html.escape(brain)}</span>'
            f'<span class="bdg {"veto" if vetoed else "ok"}">guard: {"vetoed" if vetoed else "accepted"}</span></div>')


def timeline_html(entries: list[dict]) -> str:
    rows = []
    for e in entries:
        c = AGENT_COLOURS.get(e["agent"], INK2)
        prov = f'<span class="prov">{html.escape(e["provider"])}</span>' if e.get("provider") else ""
        rows.append(f'<div class="tl {e.get("kind", "info")}"><span class="ag" style="background:{c}">'
                    f'{html.escape(e["agent"])}</span><span class="tx">{html.escape(e["text"])}{_badges(e)}</span>'
                    f'{prov}</div>')
    return '<div class="tlwrap">' + "".join(rows) + "</div>"


# ------------------------------------------------------------------ decision cards + evidence table
AI_AGENTS = ("Skeptic", "Detective", "Orchestrator")
CARD_ORDER = ("Sentinel", "Skeptic", "Detective", "Orchestrator", "Field Commander", "Auditor")


def _short(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _plain_choice(agent: str, text: str) -> str:
    """A short 'what it did' for the agents that are deterministic (no AI choice is recorded)."""
    if agent == "Sentinel":
        return "alarm" if text.startswith("Alarm") else "no alarm"
    if agent == "Field Commander":
        return "acoustic check" if "coustic" in text else "dig / repair"
    if agent == "Auditor":
        return text.split(" - ")[0].split(" — ")[0][:24]
    return "—"


def decision_cards(timeline: list[dict]) -> str:
    """The latest decision of each agent: choice, reason, who decided, fallbacks and the evidence cited."""
    latest: dict[str, dict] = {}
    for e in timeline:
        if e["agent"] in AI_AGENTS and "guard" not in (e.get("numbers") or {}):
            continue                                       # only AI-decision entries count for these agents
        if e["agent"] in CARD_ORDER:
            latest[e["agent"]] = e
    cards = []
    for agent in CARD_ORDER:
        colour = AGENT_COLOURS.get(agent, INK2)
        e = latest.get(agent)
        head = f'<div class="dch"><span class="ag" style="background:{colour}">{agent}</span>'
        if e is None:
            cards.append(f'<div class="dc idle" style="border-left-color:{colour}">{head}</div>'
                         '<div class="dcc">not run yet</div></div>')
            continue
        nums = e.get("numbers") or {}
        ai = agent in AI_AGENTS
        brain = brain_of(e) if ai else "rules"
        guard = str(nums.get("guard", "")) if ai else ""
        vetoed = guard.startswith("vetoed")
        choice = (str(nums.get("ai_choice")) if ai else _plain_choice(agent, e["text"]))
        if vetoed:
            choice += f" → {nums.get('rules_default')} (rule veto)"
        badges = f'<span class="bdg {"ai" if brain.startswith("AI") else "rules"}">{html.escape(brain)}</span>'
        if ai:
            badges += f'<span class="bdg {"veto" if vetoed else "ok"}">guard: {"vetoed" if vetoed else "accepted"}</span>'
        after = (e.get("provider") or "")
        fallbacks = [s.strip() for s in after.split("(after:", 1)[1].rstrip(") ").split(";")] if "(after:" in after else []
        foot = []
        if ai:
            cited = nums.get("cited") or []
            foot.append("<b>cited:</b> " + (html.escape(_short("; ".join(cited), 120)) if cited else "nothing quoted"))
        if fallbacks:
            foot.append(f"<b>fallbacks ({len(fallbacks)}):</b> {html.escape(_short(fallbacks[0], 70))}")
        cards.append(
            f'<div class="dc" style="border-left-color:{colour}">{head}{badges}</div>'
            f'<div class="dcc">{html.escape(_short(choice, 60))}</div>'
            f'<div class="dcr" title="{html.escape(e["text"])}">{html.escape(e["text"])}</div>'
            f'<div class="dcf">{"<br>".join(foot)}</div></div>')
    return '<div class="cards">' + "".join(cards) + "</div>"


SUPPORT_CHIPS = {"leak": ("leak", "chip-leak"), "against": ("against", "chip-against"),
                 "neutral": ("neutral", "chip-neutral"), "fixed": ("fixed ✓", "chip-fixed"),
                 "vetoed by rule": ("vetoed by rule", "chip-veto")}


def ledger_html(rows: list[dict]) -> str:
    """The evidence ledger as a table: coloured 'supports' chips, reliability, source tool."""
    body = []
    for r in rows:
        label, cls = SUPPORT_CHIPS.get(r.get("supports", ""), (r.get("supports", ""), "chip-neutral"))
        body.append(f'<tr><td class="w">{html.escape(r.get("when", ""))}</td>'
                    f'<td class="d">{html.escape(r["dimension"])}</td><td>{html.escape(r["finding"])}</td>'
                    f'<td><span class="chip {cls}">{html.escape(label)}</span></td>'
                    f'<td class="rel">{html.escape(r.get("reliability", ""))}</td>'
                    f'<td class="src">{html.escape(r.get("source", ""))}</td></tr>')
    head = "".join(f"<th>{h}</th>" for h in ("When", "Dimension", "Finding", "Supports", "Reliability", "Source tool"))
    return f'<div class="ledgerwrap"><table class="ledger"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'



def evidence_card(case_id: str, tier: str, zone: str, excess: float, dips: list, masked: list, ops: str,
                  areas: list[dict], next_step: str) -> str:
    dip = ", ".join(f"−{d:.2f} m at S{s}" for s, d in dips[:2]) if dips else "—"
    mask = f" ({', '.join(masked)} masked)" if masked else ""
    ar = " · ".join(f"{a['area_id']} {a['likelihood']:.0%}" for a in areas[:3]) if areas else "—"
    lines = [f"<b>Case {html.escape(case_id)} · {html.escape(tier)}</b>",
             f"Zone {zone} inflow: <b>{excess:+.1f} L/s</b> vs normal",
             f"Pressure: {dip}{mask}", f"Ops check: {html.escape(ops)}", f"Areas (relative likelihood): {ar}",
             f"Next: {html.escape(next_step)}"]
    return '<div class="card">' + "<br>".join(lines) + "</div>"


CSS = """
<style>
.block-container{padding-top:1.2rem;padding-bottom:1rem;max-width:1500px}
h1{font-size:1.7rem !important;letter-spacing:-.02em}
.kpi{border:1px solid #e3e2dc;border-radius:10px;padding:8px 12px;background:#fff;min-height:80px;box-sizing:border-box}
.kpi .v{font-size:1.35rem;font-weight:700;color:#1d5aa6;line-height:1.1}
.kpi .l{font-size:.75rem;color:#52514e}
.tlwrap{max-height:520px;overflow-y:auto;padding-right:4px}
.tl{display:flex;gap:8px;align-items:flex-start;padding:6px 4px;border-bottom:1px solid #f0efea;font-size:.86rem;line-height:1.35}
.tl .ag{color:#fff;border-radius:6px;padding:1px 7px;font-size:.72rem;font-weight:700;white-space:nowrap;margin-top:1px}
.tl .tx{flex:1;color:#0b0b0b}
.tl .prov{font-size:.68rem;color:#8f8e87;white-space:nowrap}
.tx .bd{margin-top:4px}
.bdg{display:inline-block;white-space:nowrap;border-radius:5px;padding:1px 7px;margin-right:5px;font-size:.72rem;font-weight:700;border:1px solid}
.bdg.ai{background:#e8f0fb;color:#14468a;border-color:#1d5aa6}
.bdg.rules{background:#efeee9;color:#3d3c39;border-color:#8f8e87}
.bdg.ok{background:#eaf6ee;color:#14692d;border-color:#1a8a3c}
.bdg.veto{background:#fbe9e9;color:#9b1f1f;border-color:#c73636}
.tl.verdict{background:#f4faf5}.tl.alert{background:#fdf6f6}.tl.human{background:#fbf5e8}
.card{font-family:'DejaVu Sans Mono',monospace;font-size:.8rem;line-height:1.55;border:1.5px solid #1d5aa6;
      border-radius:10px;padding:10px 12px;background:#f6f9fe}
.maplegend{display:flex;gap:8px;align-items:center;font-size:.62rem;color:#3d3c39;white-space:nowrap;overflow:hidden;margin-top:2px}
.maplegend i{display:inline-block;vertical-align:middle;margin-right:3px}
.cards{display:grid;grid-template-columns:repeat(6,1fr);gap:8px}
.dc{border:1px solid #e3e2dc;border-left:5px solid #ccc;border-radius:8px;padding:6px 9px;background:#fff;min-height:132px}
.dc.idle{background:#faf9f6;color:#8f8e87}
.dch{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:3px}
.dch .ag{color:#fff;border-radius:6px;padding:1px 7px;font-size:.72rem;font-weight:700}
.dcc{font-weight:700;font-size:.86rem;color:#0b0b0b;margin:1px 0}
.dcr{font-size:.76rem;line-height:1.3;color:#2d2c2a;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.dcf{font-size:.68rem;color:#52514e;margin-top:3px;line-height:1.3}
.ledgerwrap{max-height:440px;overflow:auto;border:1px solid #e3e2dc;border-radius:8px}
table.ledger{border-collapse:collapse;width:100%;font-size:.78rem}
table.ledger th{position:sticky;top:0;background:#f4f3ee;text-align:left;padding:5px 8px;font-size:.72rem;color:#52514e;border-bottom:1px solid #e3e2dc}
table.ledger td{padding:5px 8px;border-bottom:1px solid #f0efea;vertical-align:top;color:#0b0b0b}
table.ledger td.w,table.ledger td.src{white-space:nowrap;color:#52514e}
table.ledger td.d{font-weight:600;white-space:nowrap}
table.ledger td.rel{color:#52514e;font-size:.72rem}
.chip{display:inline-block;border-radius:10px;padding:1px 9px;font-weight:700;font-size:.72rem;white-space:nowrap;border:1px solid}
.chip-leak{background:#fbe9e9;color:#9b1f1f;border-color:#c73636}
.chip-against{background:#eaf6ee;color:#14692d;border-color:#1a8a3c}
.chip-neutral{background:#efeee9;color:#3d3c39;border-color:#a9a8a1}
.chip-fixed{background:#1a8a3c;color:#fff;border-color:#1a8a3c}
.chip-veto{background:#fff;color:#9b1f1f;border-color:#c73636;border-style:dashed}
.kcol{background:#f6f5f1;border-radius:10px;padding:8px;min-height:120px}
.khead{font-weight:700;font-size:.8rem;color:#2d2c2a;margin-bottom:6px;display:flex;justify-content:space-between}
.kcount{background:#e3e2dc;border-radius:10px;padding:0 8px;font-size:.72rem}
.kcard{background:#fff;border:1px solid #e3e2dc;border-radius:8px;padding:6px 8px;margin-bottom:6px}
.kcard.kactive{border:2px solid #1d5aa6}
.kid{font-weight:700;font-size:.78rem;display:flex;justify-content:space-between;gap:4px;align-items:center}
.kmeta{font-size:.72rem;color:#52514e;line-height:1.35}
.kempty{font-size:.72rem;color:#a9a8a1;text-align:center;padding:10px 0}
.vchip{border-radius:9px;padding:0 7px;font-size:.66rem;font-weight:700;border:1px solid;white-space:nowrap}
.vc-fixed{background:#eaf6ee;color:#14692d;border-color:#1a8a3c}
.vc-bad{background:#fbe9e9;color:#9b1f1f;border-color:#c73636}
.vc-none{background:#efeee9;color:#3d3c39;border-color:#a9a8a1}
.vc-open{background:#e8f0fb;color:#14468a;border-color:#1d5aa6}
.badge{display:inline-block;border-radius:12px;padding:2px 10px;font-weight:700;font-size:.8rem;margin-right:6px}
.approve{border:2px solid #b87800;background:#fbf5e8;border-radius:10px;padding:10px 12px;margin-bottom:8px}
</style>
"""
