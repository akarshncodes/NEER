"""Dashboard tab "Dataset": the demo data behind NEER - where it comes from, what is in it, and the raw numbers."""
from __future__ import annotations

import io
import zipfile

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from neer import config
from neer.app import components as C

DATA = config.ROOT / "dataset"
BADGES = [("#0b3a66", "Network: EPA Net3 (real, public)"), ("#7c3aed", "Readings: simulated in WNTR / EPANET"),
          ("#b45309", "Events: injected & hidden from NEER"), ("#15803d", "Seed 7 - identical every run")]


@st.cache_data(show_spinner=False)
def _csv(rel: str) -> pd.DataFrame:
    return pd.read_csv(DATA / rel)


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(DATA.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(DATA.parent))
    return buf.getvalue()


def _inflow_chart(zone: str, reveal: bool) -> go.Figure:
    df = _csv("live_city/scada_zone_inflow_hourly.csv")
    col = f"{zone}_net_inflow_lps"
    x = df["day"] + df["hour"] / 24
    night = df["hour"].between(2, 4)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=df[col], mode="lines", line=dict(width=1, color="#94a3b8"), name="every hour"))
    fig.add_trace(go.Scatter(x=x[night], y=df[col][night], mode="markers", marker=dict(size=5, color="#0b3a66"),
                             name="02:00–04:00 (night scan)"))
    hist_days = df.loc[df["certified_clean_history"] == 1, "day"].max()
    fig.add_vrect(x0=df["day"].min(), x1=hist_days + 1, fillcolor="#bbf7d0", opacity=0.25, line_width=0,
                  annotation_text="certified-clean history", annotation_position="top left")
    if reveal:
        for _, r in _csv("live_city/hidden_truth_JUDGES_ONLY.csv").iterrows():
            fig.add_vline(x=r["day"], line_dash="dot", line_color="#dc2626")
            fig.add_annotation(x=r["day"], y=1, yref="paper", text=str(r["hidden_event"])[:24], showarrow=False,
                               textangle=-90, font=dict(size=9, color="#dc2626"), xanchor="left", yanchor="top")
    fig.update_xaxes(title="simulation day")
    fig.update_yaxes(title="L/s")
    fig = C._layout(fig, 330, f"Zone {zone}: raw hourly inflow (L/s) over 37 days")
    fig.update_layout(legend=dict(orientation="h", y=-0.25))
    return fig


def _pressure_heatmap() -> go.Figure:
    df = _csv("live_city/scada_pressure_hourly.csv")
    at3 = df[df["hour"] == 3].set_index("day").drop(columns=["hour", "certified_clean_history"])
    base = at3.iloc[:7].mean()
    delta = (at3 - base).T
    fig = go.Figure(go.Heatmap(z=delta.values, x=delta.columns, y=[c.replace("_m", "") for c in delta.index],
                               colorscale="RdBu", zmid=0, colorbar=dict(title="Δ m<br>(red = drop)")))
    fig.update_xaxes(title="simulation day")
    return C._layout(fig, 360, "Pressure at 03:00 vs the clean-history average, per sensor (m)")


def render(reveal: bool) -> None:
    if not (DATA / "MANIFEST.csv").exists():
        st.warning("Dataset not built yet. Run `uv run python scripts/build_dataset.py`.")
        return
    st.markdown(" ".join(f'<span class="nw-pill" style="background:{c};border-radius:999px;padding:3px 10px;color:#fff;'
                         f'font-size:.74rem;font-weight:700;margin-right:6px">{t}</span>' for c, t in BADGES),
                unsafe_allow_html=True)
    st.caption("The network is the US EPA's public Net3 benchmark. The hourly readings are simulated by the EPA's "
               "hydraulic engine with realistic noise, and the events are injected at known places and times, so "
               "every NEER decision can be scored against the truth. Not field data; the next step is BattLeDIM L-Town.")
    man = _csv("MANIFEST.csv")
    st.markdown(C.kpi_strip([("Files", len(man)), ("Rows", f"{int(man['rows'].sum()):,}"), ("Junctions", 92),
                             ("Pipes", 117), ("Zones", 5), ("Zone meters", 15), ("Pressure sensors", 20),
                             ("Live-city days", 37)], highlight=1), unsafe_allow_html=True)

    c1, c2 = st.columns([1.35, 1], gap="large")
    with c1:
        zone = st.segmented_control("Zone", ["Z1", "Z2", "Z3", "Z4", "Z5"], default="Z1", key="ds_zone") or "Z1"
        st.plotly_chart(_inflow_chart(zone, reveal), width="stretch", config={"displayModeBar": False})
        st.caption("Each dark dot is an hour inside the 02:00–04:00 night-scan window. A step up in the dots that "
                   "stays up is a leak; a spike in the grey daytime line that is gone by night is a look-alike."
                   + ("" if reveal else " Turn on 'Reveal true leak (judges only)' to see the hidden events."))
    with c2:
        st.plotly_chart(_pressure_heatmap(), width="stretch", config={"displayModeBar": False})

    st.markdown("#### Browse any file")
    f1, f2 = st.columns([1.2, 1])
    files = [f for f in man["file"] if reveal or "JUDGES_ONLY" not in f]
    pick = f1.selectbox("File", files, index=files.index("live_city/night_scan_0200_0400.csv")
                        if "live_city/night_scan_0200_0400.csv" in files else 0, key="ds_file")
    df = _csv(pick)
    f2.download_button("Download this CSV", df.to_csv(index=False).encode(), file_name=pick.replace("/", "__"),
                       mime="text/csv", width="stretch")
    f2.download_button("Download the whole dataset (ZIP)", _zip(), file_name="neer_dataset.zip",
                       mime="application/zip", width="stretch")
    st.caption(f"{pick}: {len(df):,} rows × {df.shape[1]} columns. Also served by the API at "
               f"`GET /api/dataset/{pick}`.")
    st.dataframe(df.head(300), hide_index=True, width="stretch", height=320)
    with st.expander("Data dictionary (dataset/README.md)"):
        st.markdown((DATA / "README.md").read_text())
