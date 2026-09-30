"""Building blocks for the NEER Control Room (figures + small HTML pieces)."""
from __future__ import annotations

import html
from typing import Optional

import numpy as np
import plotly.graph_objects as go

from neer import config
from neer.app.theme import CSS, T, css  # noqa: F401 - re-exported for the dashboard

ZONE_COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
AGENT_COLOURS = {"Sentinel": "#0e8fa3", "Skeptic": "#c73636", "Detective": "#2a78d6", "Orchestrator": "#1d3f8a",
                 "Field Commander": "#8a3fb0", "Auditor": "#1a8a3c", "Supervisor": "#b87800"}


def _layout(fig: go.Figure, height: int, title: str = "") -> go.Figure:
    c = T()
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=36 if title else 8, b=8), paper_bgcolor=c["surface"],
                      plot_bgcolor=c["surface"], title=dict(text=title, font=dict(size=14, color=c["ink"]), x=0.01),
                      font=dict(family="Geist, sans-serif", size=12, color=c["muted"]), showlegend=True,
                      legend=dict(orientation="h", y=-0.02, x=0, font=dict(size=11)))
    return fig


def water_bill(days_inflow: list[np.ndarray], normal: np.ndarray, sd: np.ndarray, zone: str,
               day_labels: list[str], height: int = 260) -> go.Figure:
    """Extra water entering the zone each hour (inflow minus normal) vs the normal wobble band (±2 sd)."""
    c = T()
    fig = go.Figure()
    n = len(days_inflow)
    x = np.arange(n * config.HOURS)
    extra = np.concatenate([d - normal for d in days_inflow])
    band = np.tile(2 * sd, n)
    fig.add_trace(go.Scatter(x=np.r_[x, x[::-1]], y=np.r_[band, -band[::-1]], fill="toself",
                             fillcolor=c["plot_fill"], line=dict(width=0), name="Normal wobble (±2 sd)",
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=extra, mode="lines", line=dict(color=c["accent"], width=2),
                             name="Extra water (L/s)"))
    for i in range(n):
        fig.add_vline(x=i * config.HOURS - 0.5, line=dict(color=c["line"], width=1))
    fig.update_xaxes(tickvals=[i * config.HOURS + 12 for i in range(n)], ticktext=day_labels, gridcolor=c["line"])
    fig.update_yaxes(title="L/s above normal", gridcolor=c["line"], zeroline=True, zerolinecolor=c["line2"])
    return _layout(fig, height, f"Zone {zone}: water nobody paid for")


# ------------------------------------------------------------------ auditor meter
def auditor_meter(llr: list[float], height: int = 220) -> go.Figure:
    c = T()
    thr = float(np.log(config.SPRT_ODDS))
    thr_fixed = float(np.log(config.SPRT_ODDS_FIXED))
    fig = go.Figure()
    fig.add_hrect(y0=thr, y1=max(thr * 1.6, max(llr + [0]) + 1), fillcolor=c["bad_soft"], line_width=0)
    fig.add_hrect(y0=min(-thr_fixed * 1.3, min(llr + [0]) - 1), y1=-thr_fixed, fillcolor=c["good_soft"], line_width=0)
    fig.add_trace(go.Scatter(x=list(range(1, len(llr) + 1)), y=llr, mode="lines+markers",
                             line=dict(color=c["ink"], width=2), marker=dict(size=5), name="Evidence"))
    fig.add_hline(y=thr, line=dict(color=c["bad"], dash="dash"), annotation_text="leak still there (99:1)",
                  annotation_position="top left", annotation_font_color=c["bad"])
    fig.add_hline(y=-thr_fixed, line=dict(color=c["good"], dash="dash"), annotation_text="FIXED (999:1)",
                  annotation_position="bottom left", annotation_font_color=c["good"])
    fig.update_xaxes(title="hours after repair", gridcolor=c["line"], dtick=1)
    fig.update_yaxes(title="evidence", gridcolor=c["line"], zeroline=True, zerolinecolor=c["line2"])
    fig = _layout(fig, height, "Auditor: hour-by-hour proof")
    fig.update_layout(showlegend=False)
    return fig


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
        c = AGENT_COLOURS.get(e["agent"], T()["muted"])
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
    return "-"


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
        colour = AGENT_COLOURS.get(agent, T()["muted"])
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
    dip = ", ".join(f"-{d:.2f} m at S{s}" for s, d in dips[:2]) if dips else "-"
    mask = f" ({', '.join(masked)} masked)" if masked else ""
    ar = " · ".join(f"{a['area_id']} {a['likelihood']:.0%}" for a in areas[:3]) if areas else "-"
    lines = [f"<b>Case {html.escape(case_id)} · {html.escape(tier)}</b>",
             f"Zone {zone} inflow: <b>{excess:+.1f} L/s</b> vs normal",
             f"Pressure: {dip}{mask}", f"Ops check: {html.escape(ops)}", f"Areas (relative likelihood): {ar}",
             f"Next: {html.escape(next_step)}"]
    return '<div class="card">' + "<br>".join(lines) + "</div>"


def kpi_strip(items: list[tuple[str, str]], highlight: int | None = None, wide: tuple[int, ...] = ()) -> str:
    """One bordered strip of figures separated by hairlines: (label, value) pairs. Mono numbers, muted labels."""
    cells = "".join(f'<div class="kcell{" wide" if i in wide else ""}{" hl" if i == highlight else ""}">'
                    f'<div class="v">{html.escape(str(v))}</div><div class="l">{html.escape(l)}</div></div>'
                    for i, (l, v) in enumerate(items))
    cols = " ".join("1.9fr" if i in wide else "1fr" for i in range(len(items)))
    return f'<div class="kstrip" style="grid-template-columns:{cols}">{cells}</div>'
