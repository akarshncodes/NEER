"""The 3D city view: the case drawn as a tilted, extruded city (pydeck / deck.gl). Display only.

It draws the same `opsmap.Layers` the 2D operations map uses, so nothing here is invented:
- pipes (PathLayer), coloured by zone; the case zone at full colour, the others faded;
- every junction as an extruded column (ColumnLayer): height and colour from the case's relative likelihood
  (the Detective's posterior). Junctions in the suspected areas are tall and red / orange; the rest are low and blue-grey;
- the search area (blue), quiet areas (grey) and the repaired area (green) as translucent rings (PolygonLayer);
- pressure sensors as small dots, zone names as text, and the true leak only when "reveal" is on.

Note: pydeck turns every string prop into a data expression ("@@=..."), so only accessors (get_*) take strings
here; units are left at deck.gl's default, metres.
Deck.gl is bundled with Streamlit, so the layers render offline; only the Carto basemap tiles need the network.
The placement is illustrative (EPA Net3 on Madurai), exactly as on the 2D map.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pydeck as pdk

from neer.app import geo
from neer.app.components import ZONE_COLOURS
from neer.app.opsmap import Layers, _bbox, _zoom_for, pipe_width
from neer.app.theme import T
from neer.sim.network import get_network

COLUMN_RADIUS_M = 30
MAX_HEIGHT_M = 750.0                 # the most likely junction's column (display scale only)
LOW_HEIGHT_M = 140.0                 # junctions outside the suspected areas stay low
CAPTION = ("Drag to pan · Ctrl + drag (or right-drag) to tilt and rotate · scroll to zoom. "
           "Column height = relative likelihood (not calibrated). Network placement is illustrative (EPA Net3 on Madurai).")


def rgb(hex_colour: str, a: int = 255) -> list[int]:
    h = hex_colour.lstrip("#")
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a]


def _lerp(c1: list[int], c2: list[int], t: float) -> list[int]:
    t = min(max(t, 0.0), 1.0)
    return [round(a + (b - a) * t) for a, b in zip(c1, c2)]


HOT_LOW, HOT_MID, HOT_HIGH = [255, 200, 90, 235], [247, 130, 40, 245], [224, 28, 28, 255]   # yellow -> orange -> red
COOL, COOL_HI = [96, 125, 160, 150], [74, 144, 226, 210]                                   # grey-blue -> blue
SEARCH, QUIET, FIXED, LEAK = "#1d5aa6", "#6b6a66", "#1a8a3c", "#d11a1a"


def hot(t: float) -> list[int]:
    return _lerp(HOT_LOW, HOT_MID, t * 2) if t < 0.5 else _lerp(HOT_MID, HOT_HIGH, (t - 0.5) * 2)


@dataclass
class Camera:
    """What the user chose next to the map."""
    pitch: float = 55.0
    bearing: float = -25.0
    fly_to: bool = False


class _Geo:
    """Net3 (x, y) -> [lon, lat] for every node, with the same fit as the 2D map."""

    def __init__(self) -> None:
        self.net = get_network()
        self.names = list(self.net.coords)
        self.raw = np.array([self.net.coords[n] for n in self.names], dtype=float)
        ll = geo.to_latlon(self.raw, self.raw)
        self.pos = {n: [float(p[1]), float(p[0])] for n, p in zip(self.names, ll)}

    def conv(self, xy: np.ndarray) -> list[list[float]]:
        ll = geo.to_latlon(np.atleast_2d(xy), self.raw)
        return [[float(p[1]), float(p[0])] for p in ll]

    def ring(self, junctions: list[str], pad: float = 0.45) -> list[list[float]]:
        return self.conv(geo.rounded_hull(np.array([self.net.coords[j] for j in junctions]), pad))

    def centre(self, junctions: list[str]) -> list[float]:
        return self.conv(np.array([self.net.coords[j] for j in junctions]).mean(0))[0]


def focus_area(L: Layers) -> Optional[tuple[str, list[str]]]:
    """Where "Fly to suspected area" goes: the search area, else the top candidate, else the repaired area."""
    if L.current:
        return L.current
    if L.top_areas:
        return L.top_areas[0]
    return L.repaired


def view_state(L: Layers, cam: Camera, width_px: int = 700, height_px: int = 600) -> pdk.ViewState:
    """Whole city by default; with `fly_to`, centred on the focus area at pitch 60 and closer in."""
    g = _Geo()
    target = focus_area(L) if cam.fly_to else None
    if target:
        lon, lat = g.centre(target[1])
        return pdk.ViewState(latitude=lat + 0.002, longitude=lon, zoom=14.1, pitch=60, bearing=cam.bearing)   # target sits mid-screen
    lo, hi = _bbox(g.raw, 0.05)
    (lat0, lon0), (lat1, lon1) = geo.to_latlon(np.array([lo, hi]), g.raw)
    zoom = _zoom_for(np.array([lat0, lon0]), np.array([lat1, lon1]), width_px, height_px) + 0.2    # tilt shrinks the far side
    return pdk.ViewState(latitude=(lat0 + lat1) / 2 - 0.0045, longitude=(lon0 + lon1) / 2 + 0.0055, zoom=zoom,
                         pitch=cam.pitch, bearing=cam.bearing)


def _junction_rows(g: _Geo, L: Layers) -> list[dict]:
    net = g.net
    post = None
    if L.posterior is not None:
        post = np.asarray(L.posterior, dtype=float) / max(float(np.max(L.posterior)), 1e-12)
    area_of = {j: aid for aid, js in L.top_areas for j in js}
    rows = []
    for j in net.junctions:
        rel = float(post[net.jindex[j]]) if post is not None else 0.0
        zone = net.zone_of(j) if net.node_zone[j] >= 0 else "-"
        suspected = j in area_of
        if suspected:
            height, colour = 150 + MAX_HEIGHT_M * rel, hot(rel)
        else:
            faded = L.case_zone is not None and zone != L.case_zone
            height = 40 + LOW_HEIGHT_M * rel
            colour = _lerp(COOL, COOL_HI, rel)
            if faded:
                colour = [*colour[:3], 90]
        drop = L.sensor_drop.get(j)
        rows.append(dict(id=j, pos=g.pos[j], h=float(height), c=colour, hot=suspected, rel=rel,
                         title=f"Junction {j} · zone {zone}" + (f" · area {area_of[j]}" if suspected else ""),
                         line1=f"Relative likelihood: {rel:.0%} of the top junction" if post is not None
                         else "Relative likelihood: Detective has not run yet",
                         line2=f"Night pressure drop: {drop:+.2f} m (sensor)" if drop is not None else "Pressure drop: no sensor here"))
    return rows


def build_deck(layers: Optional[Layers] = None, cam: Optional[Camera] = None, dark: Optional[bool] = None,
               basemap: bool = True, width_px: int = 700, height_px: int = 600) -> pdk.Deck:
    """Build the 3D city deck for a case. Pure: no Streamlit calls, so tests can build it without a browser."""
    L, cam = layers or Layers(), cam or Camera()
    dark = (T()["name"] == "dark") if dark is None else dark
    g = _Geo()
    net, wn = g.net, g.net.wn
    out: list[pdk.Layer] = []

    # ---- 0. a ground plate so the city reads as one block even when the basemap tiles are offline
    lo, hi = _bbox(g.raw, 0.10)
    plate = g.conv(np.array([[lo[0], lo[1]], [hi[0], lo[1]], [hi[0], hi[1]], [lo[0], hi[1]]]))
    out.append(pdk.Layer("PolygonLayer", [dict(poly=plate)], get_polygon="poly", stroked=False,
                         get_fill_color=[22, 30, 42, 120] if dark else [214, 222, 232, 90]))

    # ---- 1. zone tints under the pipes
    zones = []
    for zi, z in enumerate(net.zone_names):
        js = net.zone_junctions(z)
        on = L.case_zone is None or z == L.case_zone
        zones.append(dict(poly=g.ring(js, 0.7), fill=rgb(ZONE_COLOURS[zi], 45 if on else 16),
                          line=rgb(ZONE_COLOURS[zi], 170 if on else 60)))
    out.append(pdk.Layer("PolygonLayer", zones, get_polygon="poly", get_fill_color="fill", get_line_color="line",
                         line_width_min_pixels=1, stroked=True))

    # ---- 2. pipes coloured by zone (cross-zone pipes neutral)
    pipes = []
    for name in wn.link_name_list:
        lk = wn.get_link(name)
        s, e = lk.start_node_name, lk.end_node_name
        zs, ze = net.node_zone[s], net.node_zone[e]
        if zs == ze and zs >= 0:
            on = L.case_zone is None or net.zone_names[zs] == L.case_zone
            colour = rgb(ZONE_COLOURS[zs], 235 if on else 70)
        else:
            colour = [120, 120, 120, 150]
        pipes.append(dict(path=[g.pos[s], g.pos[e]], c=colour, w=pipe_width(getattr(lk, "diameter", None)) * 5))
    out.append(pdk.Layer("PathLayer", pipes, get_path="path", get_color="c", get_width="w",
                         width_min_pixels=1, cap_rounded=True))

    # ---- 3. case areas: quiet (grey), repaired (green), search area (blue, with a glow)
    areas = [dict(poly=g.ring(js), fill=rgb(QUIET, 40), line=rgb(QUIET, 200), w=18) for _, js in L.quiet]
    if L.repaired:
        areas.append(dict(poly=g.ring(L.repaired[1]), fill=rgb(FIXED, 60), line=rgb(FIXED, 255), w=30))
    if L.current:
        ring = g.ring(L.current[1])
        areas.append(dict(poly=ring, fill=[0, 0, 0, 0], line=rgb(SEARCH, 60), w=90))                  # glow
        areas.append(dict(poly=ring, fill=rgb(SEARCH, 45), line=rgb(SEARCH, 255), w=28))
    if areas:
        out.append(pdk.Layer("PolygonLayer", areas, get_polygon="poly", get_fill_color="fill", get_line_color="line",
                             get_line_width="w", line_width_min_pixels=2, stroked=True))

    # ---- 4. hotspot glow on the ground under the suspected area
    rows = _junction_rows(g, L)
    hot_rows = [r for r in rows if r["hot"]]
    if hot_rows:
        glow = [dict(pos=r["pos"], r=60 + 90 * r["rel"], c=[*hot(r["rel"])[:3], int(25 + 45 * r["rel"])]) for r in hot_rows]
        out.append(pdk.Layer("ScatterplotLayer", glow, get_position="pos", get_radius="r", get_fill_color="c",
                             stroked=False))

    # ---- 5. the extruded junction columns (the "buildings")
    out.append(pdk.Layer("ColumnLayer", rows, get_position="pos", get_elevation="h", elevation_scale=1,
                         radius=COLUMN_RADIUS_M, disk_resolution=12, extruded=True, get_fill_color="c",
                         pickable=True, auto_highlight=True, highlight_color=[255, 255, 255, 120],
                         material=dict(ambient=0.55, diffuse=0.6, shininess=40, specularColor=[255, 255, 255])))

    # ---- 6. pressure sensors: blue (normal) -> orange (dipping); masked = grey
    sensors = []
    for s in net.sensors:
        drop = L.sensor_drop.get(s, 0.0)
        masked = s in L.masked
        colour = rgb(QUIET, 255) if masked else _lerp(rgb("#2a78d6"), rgb("#eb6834"), drop / 0.6)
        state = "masked / unhealthy" if masked else ("dipping" if drop > 0.3 else "normal")
        sensors.append(dict(pos=g.pos[s], c=colour, title=f"Pressure sensor {s} · zone {net.zone_of(s)}",
                            line1=f"Night pressure drop: {drop:+.2f} m", line2=f"State: {state}"))
    out.append(pdk.Layer("ScatterplotLayer", sensors, get_position="pos", get_fill_color="c", get_radius=55,
                         radius_min_pixels=4, stroked=True, get_line_color=[255, 255, 255, 255],
                         line_width_min_pixels=1.5, pickable=True))

    # ---- 7. the true leak (judges only: the dashboard passes it only when "reveal" is on)
    if L.true_leaks:
        leak = [dict(pos=g.pos[n], title=f"TRUE LEAK at junction {n}", line1="Simulated ground truth (judges only)",
                     line2="The agents never see this") for n in L.true_leaks if n in g.pos]
        out.append(pdk.Layer("ScatterplotLayer", leak, get_position="pos", get_radius=140,
                             filled=False, stroked=True, get_line_color=rgb(LEAK), line_width_min_pixels=3))
        out.append(pdk.Layer("ColumnLayer", leak, get_position="pos", get_elevation=MAX_HEIGHT_M * 1.35, radius=16,
                             extruded=True, get_fill_color=rgb(LEAK), pickable=True))

    # ---- 8. labels: zone names and area names
    labels = []
    for zi, z in enumerate(net.zone_names):
        js = net.zone_junctions(z)
        on = L.case_zone is None or z == L.case_zone
        labels.append(dict(pos=g.centre(js), t=z, c=[*rgb(ZONE_COLOURS[zi])[:3], 255 if on else 140], s=20))
    top_h = {r["id"]: r["h"] for r in rows}
    for tag, item, colour in (("searching", L.current, SEARCH), ("repaired", L.repaired, FIXED)):
        if item:                                                     # floats just above the area's tallest column
            z = max((top_h.get(j, 0.0) for j in item[1]), default=0.0) + 90
            labels.append(dict(pos=[*g.centre(item[1]), z], t=f"{item[0]} {tag}", c=rgb(colour), s=15))
    if L.true_leaks:
        labels += [dict(pos=[*g.pos[n], MAX_HEIGHT_M * 1.35 + 60], t="TRUE LEAK", c=rgb(LEAK), s=14) for n in L.true_leaks if n in g.pos]
    out.append(pdk.Layer("TextLayer", labels, get_position="pos", get_text="t", get_color="c", get_size="s",
                         font_weight=700, billboard=True, font_settings={"sdf": True}, outline_width=4,
                         outline_color=[0, 0, 0, 220] if dark else [255, 255, 255, 235], get_pixel_offset=[0, -18]))

    style = (pdk.map_styles.CARTO_DARK if dark else pdk.map_styles.CARTO_LIGHT) if basemap else None
    return pdk.Deck(layers=out, initial_view_state=view_state(L, cam, width_px, height_px), map_style=style,
                    tooltip={"html": "<b>{title}</b><br/>{line1}<br/>{line2}", "style": {"fontFamily": "Geist, sans-serif", "fontSize": "12px",
                                                         "backgroundColor": "#10151c", "color": "#ffffff"}})


def legend_html() -> str:
    """One compact row under the 3D map."""
    sw = lambda c, extra="": f'<i style="background:{c};{extra}"></i>'          # noqa: E731
    items = [
        sw("linear-gradient(90deg,#ffc85a,#f78228,#e01c1c)", "width:22px;height:8px") + "suspected (tall = more likely)",
        sw("#4a90e2", "width:9px;height:9px") + "other junctions",
        sw("#2a78d6", "width:9px;height:9px;border-radius:50%") + sw("#eb6834", "width:9px;height:9px;border-radius:50%") + "sensor",
        sw(SEARCH, "width:14px;height:4px") + "searching",
        sw(QUIET, "width:14px;height:4px") + "quiet",
        sw(FIXED, "width:14px;height:4px") + "repaired",
    ]
    return '<div class="maplegend">' + "".join(f"<span>{i}</span>" for i in items) + "</div>"


# ====================================================================== blueprint mode
# A "blueprint on the table" look: white wireframe city blocks on a dark board, pipes drawn as thin
# drafting lines, and the suspected leak pipes glowing red/orange. The blocks are illustrative (one block
# per junction, deterministic heights) - the pipes, areas, likelihoods and sensors are the real case data.
BP_BOARD = [8, 24, 44, 255]
BP_GRID = [120, 170, 220, 40]
BP_LINE = [225, 238, 250, 230]
BP_PIPE = [150, 200, 240, 170]
BP_HOT = [255, 90, 40, 255]
BP_GLOW = [255, 120, 40, 70]


def _block(lon: float, lat: float, half_m: float) -> list[list[float]]:
    dlat = half_m / 111_000
    dlon = half_m / (111_000 * np.cos(np.radians(lat)))
    return [[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat], [lon - dlon, lat + dlat]]


def build_blueprint(layers: Optional[Layers] = None, cam: Optional[Camera] = None,
                    width_px: int = 700, height_px: int = 600) -> pdk.Deck:
    """The blueprint-style 3D view (no basemap, so it works fully offline)."""
    L, cam = layers or Layers(), cam or Camera()
    g = _Geo()
    net, wn = g.net, g.net.wn
    out: list[pdk.Layer] = []

    # the board + a drafting grid
    lo, hi = _bbox(g.raw, 0.12)
    board = g.conv(np.array([[lo[0], lo[1]], [hi[0], lo[1]], [hi[0], hi[1]], [lo[0], hi[1]]]))
    out.append(pdk.Layer("PolygonLayer", [dict(poly=board)], get_polygon="poly", stroked=True,
                         get_fill_color=BP_BOARD, get_line_color=BP_LINE, line_width_min_pixels=2))
    grid = []
    for t in np.linspace(0, 1, 25):
        x = lo[0] + (hi[0] - lo[0]) * t
        y = lo[1] + (hi[1] - lo[1]) * t
        grid.append(dict(p=g.conv(np.array([[x, lo[1]], [x, hi[1]]]))))
        grid.append(dict(p=g.conv(np.array([[lo[0], y], [hi[0], y]]))))
    out.append(pdk.Layer("PathLayer", grid, get_path="p", get_color=BP_GRID, get_width=1, width_min_pixels=1))

    # which junctions are suspected (candidate / current area) and how strongly
    rows = {r["id"]: r for r in _junction_rows(g, L)}
    hot_j = {j for _, js in L.top_areas for j in js} | (set(L.current[1]) if L.current else set())
    fixed_j = set(L.repaired[1]) if L.repaired else set()

    # wireframe city blocks, one per junction (illustrative)
    blocks = []
    for j in net.junctions:
        lon, lat = g.pos[j]
        h = 50 + (int(j) * 37 % 7) * 28
        is_hot = j in hot_j
        line = BP_HOT if is_hot else ([90, 220, 140, 255] if j in fixed_j else BP_LINE)
        fill = [255, 110, 50, int(40 + 90 * rows[j]["rel"])] if is_hot else [200, 225, 255, 14]
        blocks.append(dict(poly=_block(lon, lat, 32), h=h + (180 * rows[j]["rel"] if is_hot else 0), line=line,
                           fill=fill, title=rows[j]["title"], line1=rows[j]["line1"], line2=rows[j]["line2"]))
    out.append(pdk.Layer("PolygonLayer", blocks, get_polygon="poly", extruded=True, wireframe=True,
                         get_elevation="h", get_fill_color="fill", get_line_color="line", pickable=True,
                         auto_highlight=True, highlight_color=[255, 255, 255, 90]))

    # pipes: drafting lines; pipes inside the suspected area glow
    cold, glow = [], []
    for name in wn.link_name_list:
        lk = wn.get_link(name)
        s, e = lk.start_node_name, lk.end_node_name
        seg = dict(path=[g.pos[s], g.pos[e]])
        (glow if (s in hot_j or e in hot_j) and s in net.jindex and e in net.jindex else cold).append(seg)
    out.append(pdk.Layer("PathLayer", cold, get_path="path", get_color=BP_PIPE, get_width=6, width_min_pixels=1.2))
    if glow:
        out.append(pdk.Layer("PathLayer", glow, get_path="path", get_color=BP_GLOW, get_width=60, width_min_pixels=8,
                             cap_rounded=True))
        out.append(pdk.Layer("PathLayer", glow, get_path="path", get_color=BP_HOT, get_width=14, width_min_pixels=3,
                             cap_rounded=True))

    # sensors: small cyan dots
    out.append(pdk.Layer("ScatterplotLayer", [dict(pos=g.pos[s]) for s in net.sensors], get_position="pos",
                         get_radius=30, radius_min_pixels=2.5, get_fill_color=[90, 220, 255, 255]))

    # labels, drafting style ("tunnel ->" in the reference)
    labels = [dict(pos=g.centre(net.zone_junctions(z)), t=f"ZONE {z}", c=[210, 230, 250, 200], s=15)
              for z in net.zone_names]
    focus = focus_area(L)
    if focus:
        tag = "REPAIRED" if L.repaired and focus[0] == L.repaired[0] else "LEAK SUSPECTED"
        top = max((b["h"] for b, j in zip(blocks, net.junctions) if j in focus[1]), default=100)
        labels.append(dict(pos=[*g.centre(focus[1]), top + 80], t=f"{tag}  {focus[0]}  ←", c=BP_HOT if tag != "REPAIRED"
                           else [90, 220, 140, 255], s=17))
    if L.true_leaks:
        labels += [dict(pos=[*g.pos[n], 420], t="TRUE LEAK", c=[255, 60, 60, 255], s=14) for n in L.true_leaks if n in g.pos]
        out.append(pdk.Layer("ColumnLayer", [dict(pos=g.pos[n]) for n in L.true_leaks if n in g.pos], get_position="pos",
                             get_elevation=400, radius=10, extruded=True, get_fill_color=[255, 60, 60, 255]))
    out.append(pdk.Layer("TextLayer", labels, get_position="pos", get_text="t", get_color="c", get_size="s",
                         font_weight=700, billboard=True, font_settings={"sdf": True}, outline_width=3,
                         outline_color=[8, 24, 44, 255], get_pixel_offset=[0, -14]))
    return pdk.Deck(layers=out, initial_view_state=view_state(L, cam, width_px, height_px), map_style=None,
                    tooltip={"html": "<b>{title}</b><br/>{line1}<br/>{line2}",
                             "style": {"backgroundColor": "#0b1e33", "color": "#e6f0fa", "fontSize": "12px"}})
