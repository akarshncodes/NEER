"""The operations map: the Net3 network on a Madurai basemap ("city") or on plain axes ("schematic").

Display only. Nothing here changes engine logic: it draws what the case state and the world already know.
Both modes are drawn by the same layer code; `_Canvas` hides the difference (lon/lat traces vs x/y traces).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import plotly.colors as pc
import plotly.graph_objects as go

from neer.app import geo
from neer.app.components import ZONE_COLOURS
from neer.sim.network import Network, get_network

LIKELIHOOD_SCALE = [[0, "#fffaf0"], [0.45, "#f7a541"], [1, "#d11a1a"]]       # white -> orange -> red
GREY, INK = "#6b6a66", "#0b0b0b"
BLUE, ORANGE, GREEN, CREW, RED = "#2a78d6", "#eb6834", "#1a8a3c", "#8a3fb0", "#d11a1a"
CAPTION = "Network placement is illustrative (EPA Net3 on a Madurai basemap)"


def rgba(hex_colour: str, a: float) -> str:
    h = hex_colour.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def mix(c1: str, c2: str, t: float) -> str:
    a = [int(c1.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(c2.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def pipe_width(diameter_m: Optional[float]) -> float:
    """Mains thick, service pipes thin (Net3 diameters run from 0.2 m to 2.5 m)."""
    if diameter_m is None:
        return 3.0
    return 1.3 if diameter_m < 0.25 else 2.0 if diameter_m < 0.31 else 3.0 if diameter_m < 0.41 else 4.5 if diameter_m < 0.8 else 6.5


@dataclass
class Layers:
    """Everything the case knows that the map can show (all optional)."""
    posterior: Optional[np.ndarray] = None
    top_areas: list[tuple[str, list[str]]] = field(default_factory=list)          # (area id, junctions), best first
    current: Optional[tuple[str, list[str]]] = None
    quiet: list[tuple[str, list[str]]] = field(default_factory=list)
    repaired: Optional[tuple[str, list[str]]] = None
    true_leaks: list[str] = field(default_factory=list)
    case_zone: Optional[str] = None
    sensor_drop: dict[str, float] = field(default_factory=dict)                     # night pressure drop in metres
    masked: list[str] = field(default_factory=list)
    crew: bool = False


class _Canvas:
    """Draws one layer in either mode. Positions are (px, py) = (lon, lat) for the city map, (x, y) otherwise."""

    def __init__(self, city: bool, net: Network) -> None:
        self.city, self.net = city, net
        self.names = list(net.coords)
        self.raw = np.array([net.coords[n] for n in self.names], dtype=float)
        self.fig = go.Figure()
        self._pos = {n: p for n, p in zip(self.names, self.conv(self.raw))}

    def conv(self, xy: np.ndarray) -> np.ndarray:
        xy = np.atleast_2d(xy)
        if not self.city:
            return xy
        ll = geo.to_latlon(xy, self.raw)
        return np.column_stack([ll[:, 1], ll[:, 0]])                                # (lon, lat)

    def pos(self, node: str) -> np.ndarray:
        return self._pos[node]

    def _add(self, x, y, **kw) -> None:
        kw.setdefault("showlegend", False)
        kw.setdefault("hoverinfo", "skip")
        self.fig.add_trace(go.Scattermap(lon=x, lat=y, **kw) if self.city else go.Scatter(x=x, y=y, **kw))

    def lines(self, polylines, colour: str, width: float, dash: bool = False, hover: Optional[str] = None) -> None:
        xs, ys = [], []
        for pl in polylines:
            pieces = geo.dashed(pl[0], pl[-1]) if dash else [(pl[i], pl[i + 1]) for i in range(len(pl) - 1)]
            for a, b in pieces:
                xs += [a[0], b[0], None]
                ys += [a[1], b[1], None]
        if xs:
            self._add(xs, ys, mode="lines", line=dict(color=colour, width=width), **({"text": hover, "hoverinfo": "text"} if hover else {}))

    def area(self, ring_xy: np.ndarray, line: str, fill: Optional[str], width: float, dash: bool = False) -> None:
        ring = self.conv(ring_xy)
        if fill:
            self._add(ring[:, 0], ring[:, 1], mode="lines", fill="toself", fillcolor=fill, line=dict(width=0))
        self.lines([ring], line, width, dash=False) if not dash else self.lines(
            [ring[i:i + 2] for i in range(len(ring) - 1)], line, width, dash=True)

    def dots(self, nodes_or_pos, colour, size, label=None, label_colour=INK, label_pos="middle center",
             label_size=10, opacity=1.0, hover=None) -> None:
        pts = np.array([self.pos(p) if isinstance(p, str) else p for p in nodes_or_pos]).reshape(-1, 2)
        kw: dict = dict(marker=dict(size=size, color=colour, opacity=opacity), mode="markers")
        if label is not None:
            kw.update(mode="markers+text", text=label, textposition=label_pos,
                      textfont=dict(size=label_size, color=label_colour))
        if hover is not None:
            kw.update(hovertext=hover, hoverinfo="text")
        self._add(pts[:, 0], pts[:, 1], **kw)

    def label(self, xy: np.ndarray, text: str, colour: str, size: int = 12, opacity: float = 1.0) -> None:
        p = self.conv(xy).reshape(-1, 2)
        self._add(p[:, 0], p[:, 1], mode="text", text=[text], textfont=dict(size=size, color=colour), opacity=opacity)


def _bbox(pts_xy: np.ndarray, pad: float = 0.12) -> tuple[np.ndarray, np.ndarray]:
    lo, hi = pts_xy.min(0), pts_xy.max(0)
    d = np.maximum(hi - lo, 1e-9) * pad
    return lo - d, hi + d


def _zoom_for(lo_ll: np.ndarray, hi_ll: np.ndarray, width_px: int, height_px: int) -> float:
    """Web-Mercator zoom level that fits a lat/lon box into the pixel area."""
    lat_span, lon_span = max(hi_ll[0] - lo_ll[0], 1e-6), max(hi_ll[1] - lo_ll[1], 1e-6)
    cos = math.cos(math.radians((hi_ll[0] + lo_ll[0]) / 2))
    z_lon = math.log2(width_px * 360 / (512 * lon_span))              # the map engine uses 512-px tiles
    z_lat = math.log2(height_px * 360 * cos / (512 * lat_span))
    return float(min(z_lon, z_lat, 17))


def build_map(mode: str = "city", layers: Optional[Layers] = None, view: str = "zone", uirevision: str = "neer",
              height: int = 600, width_px: int = 560) -> go.Figure:
    """Build the operations map. mode: 'city' | 'schematic'. view: 'zone' (zoom to the case zone) | 'full'."""
    L = layers or Layers()
    net = get_network()
    wn = net.wn
    cv = _Canvas(mode == "city", net)
    zn, fade = net.zone_names, L.case_zone is not None
    alpha = lambda z: 1.0 if not fade or zn[z] == L.case_zone else 0.3           # noqa: E731 - the case zone at full colour

    # ---- 1. zone polygons + big labels
    zone_pts = {}
    for zi, z in enumerate(zn):
        js = net.zone_junctions(z)
        xy = np.array([net.coords[j] for j in js])
        zone_pts[z] = xy
        a = alpha(zi)
        cv.area(geo.rounded_hull(xy, 0.7), rgba(ZONE_COLOURS[zi], 0.55 * a), rgba(ZONE_COLOURS[zi], 0.16 * a if a == 1 else 0.06), 1.6)
        cv.label(xy.mean(0), f"{z} · {len(js)} junctions", mix(ZONE_COLOURS[zi], "#000000", 0.35), 15, 1.0 if a == 1 else 0.55)

    # ---- 2. pipes: width by diameter, colour by zone, cross-zone pipes dashed
    groups: dict[tuple, list] = {}
    cross: dict[float, list] = {}
    for name in wn.link_name_list:
        lk = wn.get_link(name)
        s, e = lk.start_node_name, lk.end_node_name
        zs, ze = net.node_zone[s], net.node_zone[e]
        w = pipe_width(getattr(lk, "diameter", None))
        seg = np.array([cv.pos(s), cv.pos(e)])
        if zs != ze:
            cross.setdefault(w, []).append(seg)
        else:
            groups.setdefault((zs, w), []).append(seg)
    for (zi, w), segs in groups.items():
        cv.lines(segs, rgba(ZONE_COLOURS[zi], 0.95 * alpha(zi)), w)
    for w, segs in cross.items():
        cv.lines(segs, "#55534f", w, dash=True)
    meter_mid = [(cv.pos(wn.get_link(m).start_node_name) + cv.pos(wn.get_link(m).end_node_name)) / 2 for m in net.meters]
    cv.dots(meter_mid, "#0b0b0b", 12, label=["M"] * len(meter_mid), label_colour="#ffffff", label_size=8,
            hover=[f"Zone meter on pipe {m}" for m in net.meters])

    # ---- 3. junctions, then the likelihood heat on the top candidate areas
    for zi, z in enumerate(zn):
        js = net.zone_junctions(z)
        cv.dots(js, rgba(ZONE_COLOURS[zi], alpha(zi)), 5)
    heat_nodes: list[str] = []
    if L.posterior is not None and L.top_areas:
        post = L.posterior / max(float(L.posterior.max()), 1e-12)
        area_of = {j: aid for aid, js in L.top_areas for j in js}
        heat_nodes = list(area_of)
        p = {j: float(post[net.jindex[j]]) for j in heat_nodes}
        bins: dict[int, list] = {}
        for name in wn.link_name_list:
            lk = wn.get_link(name)
            if lk.start_node_name in p and lk.end_node_name in p:
                v = (p[lk.start_node_name] + p[lk.end_node_name]) / 2
                bins.setdefault(min(int(v * 8), 7), []).append(np.array([cv.pos(lk.start_node_name), cv.pos(lk.end_node_name)]))
        for b, segs in bins.items():
            cv.lines(segs, pc.sample_colorscale(LIKELIHOOD_SCALE, (b + 0.5) / 8)[0], 6.5)
        vals = [p[j] for j in heat_nodes]
        cv.dots(heat_nodes, [pc.sample_colorscale(LIKELIHOOD_SCALE, v)[0] for v in vals], [8 + 8 * v for v in vals],
                hover=[f"Junction {j} · {area_of[j]} · relative likelihood {p[j]:.0%} of the top junction" for j in heat_nodes])

    # ---- 4. case layers: quiet (grey dashed), repaired (green), current (glowing)
    def hull(junctions):
        return geo.rounded_hull(np.array([net.coords[j] for j in junctions]), 0.45)

    def top_of(ring_xy):
        return ring_xy[np.argmax(ring_xy[:, 1])]
    for aid, js in L.quiet:
        ring = hull(js)
        cv.area(ring, GREY, rgba(GREY, 0.14), 2.6, dash=True)
        cv.label(top_of(ring), f"{aid} quiet", GREY, 10)
    if L.repaired:
        aid, js = L.repaired
        ring = hull(js)
        cv.area(ring, GREEN, rgba(GREEN, 0.12), 4.5)
        cv.label(top_of(ring), f"✓ {aid} repaired", GREEN, 12)
    if L.current:
        aid, js = L.current
        ring = hull(js)
        cv.area(ring, rgba("#1d5aa6", 0.14), None, 16)                            # glow: wide and faint ...
        cv.area(ring, rgba("#1d5aa6", 0.30), None, 10)
        cv.area(ring, "#1d5aa6", rgba("#1d5aa6", 0.07), 4)                        # ... then the solid outline
        cv.label(top_of(ring), f"{aid} searching", "#1d5aa6", 12)

    # ---- 5. pressure sensors: blue (normal) -> orange (dipping); masked = grey with an X
    for s in net.sensors:
        drop = L.sensor_drop.get(s, 0.0)
        masked = s in L.masked
        colour = GREY if masked else mix(BLUE, ORANGE, min(max(drop / 0.6, 0.0), 1.0))
        state = "masked / unhealthy" if masked else ("dipping" if drop > 0.3 else "normal")
        tip = f"Sensor {s} · zone {net.zone_of(s)} · night change {-drop:+.2f} m · {state}"
        cv.dots([s], "#ffffff", 15, hover=[tip])
        cv.dots([s], colour, 10, hover=[tip], **({"label": ["✕"], "label_colour": "#ffffff", "label_size": 9} if masked else {}))

    # ---- 6. storage / sources, crew, revealed leak
    store = list(wn.tank_name_list) + list(wn.reservoir_name_list)
    cv.dots(store, "#14325c", 12, label=[("Tank " if n in wn.tank_name_list else "Source ") + n for n in store],
            label_pos="top center", label_size=9, label_colour="#14325c")
    if L.crew and L.current:
        c = np.array([net.coords[j] for j in L.current[1]]).mean(0)
        cv.dots([cv.conv(c)[0]], "#ffffff", 26)
        cv.dots([cv.conv(c)[0]], CREW, 19, label=["Crew"], label_pos="bottom center", label_colour=CREW, label_size=11)
    if L.true_leaks:
        ps = [cv.pos(n) for n in L.true_leaks]
        cv.dots(ps, rgba(RED, 0.30), 34)
        cv.dots(ps, "#ffffff", 20)
        cv.dots(ps, RED, 13, label=["TRUE LEAK"] * len(ps), label_pos="bottom center", label_colour=RED, label_size=11)

    # ---- 7. colour bar for the likelihood scale (a zero-size dummy trace carries it)
    if heat_nodes:
        p0 = cv.pos(heat_nodes[0]).reshape(1, 2)
        cv._add(p0[:, 0], p0[:, 1], mode="markers", opacity=0,
                marker=dict(size=1, color=[0.5], cmin=0, cmax=1, colorscale=LIKELIHOOD_SCALE, showscale=True,
                            colorbar=dict(title=dict(text="Relative likelihood (not calibrated)", side="top",
                                                     font=dict(size=11)),
                                          orientation="h", x=0.02, y=0.03, xanchor="left", yanchor="bottom",
                                          len=0.42, thickness=10, tickvals=[0, 1], ticktext=["low", "high"],
                                          bgcolor="rgba(255,255,255,0.85)", tickfont=dict(size=10))))

    # ---- layout: view, caption, no axes
    zone_xy = zone_pts.get(L.case_zone) if (view == "zone" and L.case_zone) else cv.raw
    lo, hi = _bbox(zone_xy)
    fig = cv.fig
    caption = CAPTION if cv.city else "Schematic view (EPA Net3 coordinates)"
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0), showlegend=False, paper_bgcolor="white",
                      uirevision=uirevision, font=dict(family="Inter, sans-serif", size=12, color="#52514e"),
                      annotations=[dict(text=caption, xref="paper", yref="paper", x=0.01, y=0.99, xanchor="left",
                                        yanchor="top", showarrow=False, font=dict(size=10, color="#52514e"),
                                        bgcolor="rgba(255,255,255,0.85)", borderpad=3)])
    if cv.city:
        (lat0, lon0), (lat1, lon1) = geo.to_latlon(np.array([lo, hi]), cv.raw)
        fig.update_layout(map=dict(style="open-street-map", uirevision=uirevision,
                                   center=dict(lat=(lat0 + lat1) / 2, lon=(lon0 + lon1) / 2),
                                   zoom=_zoom_for(np.array([lat0, lon0]), np.array([lat1, lon1]), width_px, height)))
    else:
        fig.update_layout(plot_bgcolor="#f7f7f4")
        fig.update_xaxes(visible=False, range=[lo[0], hi[0]], constrain="domain")
        fig.update_yaxes(visible=False, range=[lo[1], hi[1]], scaleanchor="x", constrain="domain")
    return fig


def legend_html() -> str:
    """One compact row under the map."""
    sw = lambda c, extra="": f'<i style="background:{c};{extra}"></i>'          # noqa: E731
    dot = lambda c: sw(c, "width:9px;height:9px;border-radius:50%")                 # noqa: E731
    items = [
        "Zones " + "".join(dot(c) for c in ZONE_COLOURS),
        sw("#55534f", "width:14px;height:0;border-top:3px dashed #55534f;background:none") + "M border",
        sw("linear-gradient(90deg,#fffaf0,#f7a541,#d11a1a)", "width:20px;height:8px;border:1px solid #ccc") + "likelihood",
        dot(BLUE) + dot(ORANGE) + dot(GREY) + "sensor",
        sw("#1d5aa6", "width:14px;height:4px") + "searching",
        sw(GREY, "width:14px;height:0;border-top:3px dashed #6b6a66;background:none") + "quiet",
        sw(GREEN, "width:14px;height:4px") + "✓ fixed",
        dot(CREW) + "crew",
    ]
    return '<div class="maplegend">' + "".join(f"<span>{i}</span>" for i in items) + "</div>"
