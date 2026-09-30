"""Live flowchart of the LangGraph agent graph (display only).

The layout is hand-placed to mirror `neer/agents/graph.py`. Progress comes from the graph checkpoints:
`order` is the sequence of nodes that ran, `current` the node(s) about to run (or waiting for a human).
"""
from __future__ import annotations

from typing import Optional

import plotly.graph_objects as go

from neer.app.components import AGENT_COLOURS
from neer.app.opsmap import rgba
from neer.app.theme import T

HW, HH = 0.72, 0.42                       # node half width / half height

# id: (x, y, title, owner line, who, tooltip)
NODES = {
    "sentinel": (0.9, 3, "Sentinel", "rules", "Sentinel", "Watches every zone; raises an alarm from three evidence dimensions."),
    "skeptic_gate": (3.1, 3, "Skeptic", "AI judge · rules veto", "Skeptic", "Judges competing hypotheses (leak, operation, planned work, sensor fault, temporary demand)."),
    "detective": (5.3, 3, "Detective", "AI reads map · rules", "Detective", "Localises the leak (engine) and interprets how concentrated the evidence is (AI)."),
    "orchestrator": (7.5, 3, "Orchestrator", "AI plans · guard", "Orchestrator", "Chooses the next action and WHERE to search; guard checks the target and the dig rule."),
    "skeptic_review": (9.7, 3, "Skeptic review", "AI critic", "Skeptic", "Reviews the plan before a human sees it."),
    "approve_plan": (11.9, 3, "Approve plan", "human", "Supervisor", "A human approves the search plan."),
    "field_commander": (14.1, 3, "Field Commander", "rules · safety validator", "Field Commander", "Acoustic checks and digs, only through the safety validator."),
    "auditor": (16.3, 3, "Auditor", "rules · independent", "Auditor", "Measures the loss itself; 999:1 evidence to close a case."),
    "watch": (1.9, 1, "WATCH", "no case", "Sentinel", "Dismissed or nothing unusual: keep watching."),
    "wait_day": (4.2, 1, "Wait a day", "clock", "Orchestrator", "Let one more day of SCADA data arrive."),
    "escalate": (7.5, 1, "Escalate", "to a human", "Orchestrator", "Budget used or approval refused: hand over to a supervisor."),
    "approve_dig": (10.9, 1, "Approve dig", "human · role check", "Supervisor", "A supervisor or engineer approves a dig; nobody else can."),
    "closed": (16.3, 1, "CLOSED ✓", "proven FIXED", "Auditor", "Repair verified by the independent Auditor."),
}
# (from, to, points, label, label position). The arrow head is at the last point.
EDGES = [
    ("sentinel", "skeptic_gate", [(1.62, 3), (2.38, 3)], "alarm", (2.0, 3.22)),
    ("skeptic_gate", "detective", [(3.82, 3), (4.58, 3)], "open", (4.2, 3.22)),
    ("detective", "orchestrator", [(6.02, 3), (6.78, 3)], "located", (6.4, 3.22)),
    ("orchestrator", "skeptic_review", [(8.22, 3), (8.98, 3)], "plan", (8.6, 3.22)),
    ("skeptic_review", "approve_plan", [(10.42, 3), (11.18, 3)], "ok", (10.8, 3.22)),
    ("approve_plan", "field_commander", [(12.62, 3), (13.38, 3)], "go", (13.0, 3.22)),
    ("field_commander", "auditor", [(14.82, 3), (15.58, 3)], "repaired", (15.2, 3.22)),
    ("sentinel", "watch", [(0.9, 2.58), (1.3, 1.42)], "no alarm", (0.55, 2.0)),
    ("skeptic_gate", "watch", [(2.9, 2.58), (2.3, 1.42)], "dismissed", (2.3, 2.1)),
    ("skeptic_gate", "wait_day", [(3.4, 2.58), (3.95, 1.42)], "wait", (3.95, 2.1)),
    ("detective", "wait_day", [(5.0, 2.58), (4.6, 1.42)], "gather more", (5.2, 2.0)),
    ("wait_day", "sentinel", [(4.2, 0.58), (4.2, 0.22), (0.5, 0.22), (0.5, 2.58)], "new day's data", (2.4, 0.22)),
    ("orchestrator", "escalate", [(7.5, 2.58), (7.5, 1.42)], "budget", (7.75, 2.0)),
    ("orchestrator", "approve_dig", [(7.95, 2.58), (10.4, 1.42)], "request dig", (9.9, 1.66)),
    ("approve_dig", "field_commander", [(11.45, 1.42), (13.85, 2.58)], "approved", (13.0, 1.95)),
    ("approve_dig", "escalate", [(10.18, 1), (8.22, 1)], "refused", (9.2, 1.18)),
    ("orchestrator", "field_commander", [(7.1, 2.58), (7.1, 2.05), (14.4, 2.05), (14.4, 2.58)], "next survey (plan approved)", (11.3, 2.05)),
    ("skeptic_review", "detective", [(9.4, 3.42), (9.4, 3.95), (5.6, 3.95), (5.6, 3.42)], "send back", (7.6, 3.95)),
    ("field_commander", "orchestrator", [(13.8, 3.42), (13.8, 4.45), (7.8, 4.45), (7.8, 3.42)], "acoustic no → re-plan", (10.8, 4.45)),
    ("auditor", "orchestrator", [(16.0, 3.42), (16.0, 5.1), (7.2, 5.1), (7.2, 3.42)], "NOT FIXED → re-listen", (11.6, 5.1)),
    ("auditor", "detective", [(16.6, 3.42), (16.6, 5.75), (5.0, 5.75), (5.0, 3.42)], "PARTLY FIXED → Detective", (10.8, 5.75)),
    ("auditor", "closed", [(16.3, 2.58), (16.3, 1.42)], "FIXED", (16.62, 2.0)),
]
LOOPBACKS = {("skeptic_review", "detective"), ("field_commander", "orchestrator"),
             ("auditor", "orchestrator"), ("auditor", "detective")}


def progress(history_next: list[tuple[str, ...]], status: str) -> tuple[list[str], tuple[str, ...]]:
    """From the checkpoint `next` tuples (oldest first) to (nodes that ran in order, node(s) running now).

    The last snapshot's `next` is what runs now (or waits for a human). When it is empty the case has ended:
    the end marker (CLOSED / WATCH) becomes the highlighted node."""
    seq = [n for nxt in history_next for n in nxt if not n.startswith("__")]
    if history_next and history_next[-1]:
        current = tuple(n for n in history_next[-1] if not n.startswith("__"))
        return seq[:len(seq) - len(current)], current
    end = {"closed": "closed", "watch": "watch", "no_alarm": "watch"}.get(status)
    return seq, (end,) if end else ()


def flow_figure(order: list[str], current: tuple[str, ...], height: int = 380) -> go.Figure:
    c = T()
    ORANGE, BLUE, GREYLINE = c["run"], c["accent"], c["line2"]
    visits = {n: order.count(n) for n in set(order)}
    taken = {(a, b) for a, b in zip(order, order[1:])}
    if current:                                        # the step that just ended points into the current node
        taken |= {(order[-1], c) for c in current} if order else set()
    fig = go.Figure()
    ann = []
    for a, b, pts, label, (lx, ly) in EDGES:
        hit = (a, b) in taken
        loop = (a, b) in LOOPBACKS
        colour = (ORANGE if loop else BLUE) if hit else GREYLINE
        xs, ys = zip(*pts)
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", hoverinfo="skip", showlegend=False,
                                 line=dict(color=colour, width=3 if hit else 1.3, dash="dot" if loop and not hit else "solid")))
        ann.append(dict(x=pts[-1][0], y=pts[-1][1], ax=pts[-2][0], ay=pts[-2][1], xref="x", yref="y", axref="x", ayref="y",
                        showarrow=True, arrowhead=2, arrowsize=1.1, arrowwidth=1.6, arrowcolor=colour, text=""))
        ann.append(dict(x=lx, y=ly, text=label, showarrow=False, font=dict(size=10, color=colour if hit else c["faint"]),
                        bgcolor=c["surface"], borderpad=1))
    shapes = []
    for nid, (x, y, title, owner, who, tip) in NODES.items():
        colour = AGENT_COLOURS.get(who, c["muted"])
        run, seen = nid in current, nid in visits
        fill = c["run_soft"] if run else rgba(colour, 0.16) if seen else c["surface2"]
        line = ORANGE if run else colour if seen else GREYLINE
        shapes.append(dict(type="rect", x0=x - HW, x1=x + HW, y0=y - HH, y1=y + HH, fillcolor=fill,
                           line=dict(color=line, width=4 if run else 1.8 if seen else 1.2), layer="below"))
        if visits.get(nid, 0) > 1:                                               # visit count as a small tag on the corner
            ann.append(dict(x=x + HW - 0.12, y=y + HH, text=f"<b>×{visits[nid]}</b>", showarrow=False,
                            font=dict(size=9, color="#ffffff"), bgcolor=line, borderpad=1))
        ann.append(dict(x=x, y=y + 0.08, text=f"<b>{title}</b>", showarrow=False,
                        font=dict(size=12, color=c["ink"] if (seen or run) else c["faint"])))
        ann.append(dict(x=x, y=y - 0.17, text=owner, showarrow=False, font=dict(size=9, color=c["muted"] if (seen or run) else c["faint"])))
        if run:
            tag = "CASE ENDED" if nid in ("closed", "watch") else "WAITING FOR HUMAN" if nid.startswith("approve") else "RUNNING NOW"
            ann.append(dict(x=x, y=y + HH + 0.2, text=f"<b>{tag}</b>",
                            showarrow=False, font=dict(size=9, color="#ffffff"), bgcolor=ORANGE, borderpad=2))
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers", marker=dict(size=40, opacity=0), showlegend=False,
                                 hovertext=f"{title} ({owner}): {tip}", hoverinfo="text"))
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor=c["surface"], plot_bgcolor=c["surface"],
                      shapes=shapes, annotations=ann, showlegend=False,
                      xaxis=dict(visible=False, range=[-0.2, 17.6], fixedrange=True),
                      yaxis=dict(visible=False, range=[-0.1, 6.15], fixedrange=True))
    return fig
