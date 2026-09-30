"""3D view of the digital twin: the network as a landscape, sunk where a what-if event lowers the pressure.

x, y = the EPA Net3 layout, z = the predicted pressure change (m) at every junction from the `simulate` tool.
A leak shows as a crater around its junction; sensors are drawn as diamonds, the event point as a red marker.
Only numbers from the twin are drawn.
"""
from __future__ import annotations

import plotly.graph_objects as go

from neer.sim.network import get_network

DEPTH_SCALE = 1.0          # metres of pressure drop shown as metres of depth (no exaggeration)


def _aspect(net) -> dict:
    """Keep the real map proportions on x / y, with a moderate height for the pressure axis."""
    xs = [c[0] for c in net.coords.values()]
    ys = [c[1] for c in net.coords.values()]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    m = max(w, h)
    return dict(x=1.6 * w / m, y=1.6 * h / m, z=0.5)


def pressure_landscape(junction_change_m: dict[str, float], event: dict, height: int = 520) -> go.Figure:
    net = get_network()
    wn = net.wn
    z = {n: junction_change_m.get(n, 0.0) * DEPTH_SCALE for n in net.coords}

    # pipes as 3D lines (None separates segments)
    xs, ys, zs = [], [], []
    for l in wn.link_name_list:
        link = wn.get_link(l)
        a, b = link.start_node_name, link.end_node_name
        (x1, y1), (x2, y2) = net.coords[a], net.coords[b]
        xs += [x1, x2, None]
        ys += [y1, y2, None]
        zs += [z.get(a, 0.0), z.get(b, 0.0), None]
    fig = go.Figure()
    fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", line=dict(color="#7c93b0", width=3),
                               hoverinfo="skip", name="pipes"))
    js = net.junctions
    vals = [z[j] for j in js]
    fig.add_trace(go.Scatter3d(
        x=[net.coords[j][0] for j in js], y=[net.coords[j][1] for j in js], z=vals, mode="markers",
        marker=dict(size=5, color=vals, colorscale=[[0, "#6d28d9"], [0.5, "#a78bfa"], [1, "#e0f2fe"]],
                    cmax=0, cmin=min(min(vals), -0.05), colorbar=dict(title="Δ pressure (m)", thickness=12, len=0.6)),
        text=[f"junction {j} · zone {net.zone_names[net.junction_zone[i]]}<br>Δp {vals[i]:+.2f} m" for i, j in enumerate(js)],
        hoverinfo="text", name="junctions"))
    fig.add_trace(go.Scatter3d(
        x=[net.coords[s][0] for s in net.sensors], y=[net.coords[s][1] for s in net.sensors],
        z=[z[s] for s in net.sensors], mode="markers", marker=dict(size=4, symbol="diamond", color="#f59e0b"),
        text=[f"sensor S{s}: {z[s]:+.2f} m" for s in net.sensors], hoverinfo="text", name="pressure sensors"))
    if event.get("kind") == "leak" and event.get("node") in net.coords:
        n = event["node"]
        fig.add_trace(go.Scatter3d(x=[net.coords[n][0]], y=[net.coords[n][1]], z=[z[n]], mode="markers+text",
                                   marker=dict(size=11, color="#dc2626"), text=[f"leak at {n}"],
                                   textposition="top center", name="injected leak"))
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=30, b=0), showlegend=True,
        legend=dict(orientation="h", y=0.02, x=0.02, bgcolor="rgba(255,255,255,.7)"),
        title=dict(text="3D twin: predicted pressure landscape (drag to rotate)", font=dict(size=13), x=0.01),
        scene=dict(xaxis=dict(visible=False), yaxis=dict(visible=False),
                   zaxis=dict(title="Δ pressure (m)", backgroundcolor="rgba(0,0,0,0)"),
                   aspectmode="manual", aspectratio=_aspect(net),
                   camera=dict(eye=dict(x=0.9, y=-1.25, z=0.75), center=dict(x=0, y=0, z=-0.15))),
        paper_bgcolor="rgba(0,0,0,0)")
    return fig
