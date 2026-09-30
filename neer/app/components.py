"""Building blocks for the NEER Control Room (figures + small HTML pieces)."""
from __future__ import annotations

import html
from typing import Optional

import numpy as np
import plotly.graph_objects as go

from neer import config
from neer.sim.network import get_network

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


# ------------------------------------------------------------------ network map
def network_map(posterior: Optional[np.ndarray] = None, current_area: Optional[list[str]] = None,
                quiet_areas: list[list[str]] = (), repaired_area: Optional[list[str]] = None,
                true_leaks: list[str] = (), highlight_zone: Optional[str] = None, height: int = 520) -> go.Figure:
    net = get_network()
    wn = net.wn
    xy = net.coords
    fig = go.Figure()
    # pipes
    xs, ys = [], []
    for l in wn.link_name_list:
        lk = wn.get_link(l)
        a, b = xy[lk.start_node_name], xy[lk.end_node_name]
        xs += [a[0], b[0], None]
        ys += [a[1], b[1], None]
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="#d9d8d2", width=1.4), hoverinfo="skip",
                             showlegend=False))
    # junctions by zone (+ relative-likelihood heat)
    for zi, z in enumerate(net.zone_names):
        js = [j for j in net.junctions if net.node_zone[j] == zi]
        op = 1.0 if highlight_zone in (None, z) else 0.35
        fig.add_trace(go.Scatter(x=[xy[j][0] for j in js], y=[xy[j][1] for j in js], mode="markers",
                                 marker=dict(size=6, color=ZONE_COLOURS[zi], opacity=op), name=z,
                                 text=[f"Junction {j} · {z}" for j in js], hoverinfo="text"))
    if posterior is not None:
        p = posterior / posterior.max()
        top = np.argsort(-posterior)[:25]
        fig.add_trace(go.Scatter(x=[xy[net.junctions[i]][0] for i in top], y=[xy[net.junctions[i]][1] for i in top],
                                 mode="markers", name="Relative likelihood (not calibrated)",
                                 marker=dict(size=10 + 34 * p[top], color=p[top], colorscale="Blues", cmin=0, cmax=1,
                                             opacity=0.75, line=dict(color="#1d5aa6", width=1)),
                                 text=[f"{net.junctions[i]}: {posterior[i]:.1%}" for i in top], hoverinfo="text"))
    # sensors & meters
    fig.add_trace(go.Scatter(x=[xy[s][0] for s in net.sensors], y=[xy[s][1] for s in net.sensors], mode="markers",
                             marker=dict(symbol="triangle-up", size=9, color="white", line=dict(color=INK, width=1.3)),
                             name="Pressure sensor", text=[f"Sensor {s}" for s in net.sensors], hoverinfo="text"))
    mx, my = [], []
    for l in net.meters:
        lk = wn.get_link(l)
        a, b = np.array(xy[lk.start_node_name]), np.array(xy[lk.end_node_name])
        m = (a + b) / 2
        mx.append(m[0]); my.append(m[1])
    fig.add_trace(go.Scatter(x=mx, y=my, mode="markers", marker=dict(symbol="square", size=8, color=INK),
                             name="Zone meter", text=[f"Meter on pipe {l}" for l in net.meters], hoverinfo="text"))
    # areas
    def ring(junctions, colour, name, dash):
        pts = np.array([xy[j] for j in junctions])
        c = pts.mean(0)
        span = np.ptp(np.array(list(xy.values())), axis=0).max()
        r = np.max(np.linalg.norm(pts - c, axis=1)) * 1.2 + 0.02 * span
        t = np.linspace(0, 2 * np.pi, 60)
        fig.add_trace(go.Scatter(x=c[0] + r * np.cos(t), y=c[1] + r * np.sin(t), mode="lines", name=name,
                                 line=dict(color=colour, width=2.4, dash=dash), hoverinfo="name"))
    for i, a in enumerate(quiet_areas):
        ring(a, "#c73636", "Quiet area (acoustic no)" if i == 0 else None, "dot")
    if current_area:
        ring(current_area, "#1d5aa6", "Current search area", "solid")
    if repaired_area:
        ring(repaired_area, "#1a8a3c", "Repaired area", "dash")
    if true_leaks:
        fig.add_trace(go.Scatter(x=[xy[n][0] for n in true_leaks], y=[xy[n][1] for n in true_leaks], mode="markers",
                                 marker=dict(symbol="star", size=18, color="#0b0b0b"), name="TRUE leak (reveal)"))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x")
    return _layout(fig, height)


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
    """(decisions answered by a live model, fallbacks to rules after the chain failed, rule vetoes)."""
    ai = fb = veto = 0
    for e in entries:
        brain = brain_of(e)
        if brain is None:
            continue
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
.kpi{border:1px solid #e3e2dc;border-radius:10px;padding:8px 12px;background:#fff;min-height:66px;box-sizing:border-box}
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
.badge{display:inline-block;border-radius:12px;padding:2px 10px;font-weight:700;font-size:.8rem;margin-right:6px}
.approve{border:2px solid #b87800;background:#fbf5e8;border-radius:10px;padding:10px 12px;margin-bottom:8px}
</style>
"""
