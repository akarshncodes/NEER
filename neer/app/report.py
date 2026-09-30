"""Case report (PDF): one section per case with the summary, timeline, evidence ledger and the Auditor chart.

Built with fpdf2; the chart is drawn with matplotlib. Every page says the city is simulated.
"""
from __future__ import annotations

import io
import os
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from fpdf import FPDF  # noqa: E402

from neer import config  # noqa: E402

LABEL = "Simulated city: not field data"
_FONTS = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")   # DejaVu: has ₹ ≈ → ✓


class _Pdf(FPDF):
    def header(self) -> None:
        self.set_font("DejaVu", "B", 8)
        self.set_text_color(176, 56, 56)
        self.cell(0, 5, LABEL, new_x="LMARGIN", new_y="NEXT", align="R")
        self.set_text_color(0, 0, 0)

    def footer(self) -> None:
        self.set_y(-10)
        self.set_font("DejaVu", "", 7)
        self.set_text_color(110, 110, 110)
        self.cell(0, 5, f"NEER case report · {LABEL} · page {self.page_no()}/{{nb}}", align="C")


def auditor_chart(llr: list[float]) -> bytes:
    """PNG of the Auditor's hour-by-hour evidence with its two decision lines (same story as the dashboard meter)."""
    leak, fixed = float(np.log(config.SPRT_ODDS)), float(np.log(config.SPRT_ODDS_FIXED))
    fig, ax = plt.subplots(figsize=(6.4, 2.2), dpi=150)
    if llr:
        ax.plot(range(1, len(llr) + 1), llr, "-o", color="#0b0b0b", ms=3.5, lw=1.6, label="evidence")
    else:
        ax.text(0.5, 0.5, "No Auditor evidence: no repair was verified in this case", ha="center", va="center",
                transform=ax.transAxes, color="#52514e")
    ax.axhline(leak, color="#c73636", ls="--", lw=1.2)
    ax.axhline(-fixed, color="#1a8a3c", ls="--", lw=1.2)
    ax.text(0.01, leak, "leak still there (99:1)", color="#c73636", fontsize=7, va="bottom", transform=ax.get_yaxis_transform())
    ax.text(0.01, -fixed, "FIXED (999:1)", color="#1a8a3c", fontsize=7, va="top", transform=ax.get_yaxis_transform())
    ax.set_ylim(min(-fixed * 1.3, min(llr + [0]) - 1), max(leak * 1.4, max(llr + [0]) + 1))
    if llr:
        ax.set_xticks(range(1, len(llr) + 1))
    ax.set_xlabel("hours after repair", fontsize=8)
    ax.set_ylabel("evidence", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(color="#e8e7e2", lw=0.6)
    ax.set_title("Auditor: hour-by-hour proof", fontsize=9, loc="left")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def _section(pdf: _Pdf, r: dict) -> None:
    pdf.add_page()
    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 8, f"Case {r['case_id']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 8)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 4, f"Scenario {r['scenario']} · seed {r.get('seed', '—')} · generated {datetime.now():%Y-%m-%d %H:%M}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)
    rows = [("Zone", r.get("zone") or "—"), ("Leak size", f"{r['leak_size_lps']:.1f} L/s" if r["leak_size_lps"] else "—"),
            ("Verdict", (r.get("verdict") or {"watch": "Dismissed, on watch", "no_alarm": "No alarm",
                                               "escalated": "Escalated to a supervisor"}.get(r["status"], r["status"])).replace("_", " ")),
            ("Contractor decision", r.get("contractor") or "—"), ("Acoustic visits / re-plans", f"{r['visits']} / {r['replans']}"),
            ("Water saved", f"{r['kpi']['litres_saved_per_day'] / 1000:,.0f} m³/day"),
            ("Crew-hours", f"{r['kpi']['crew_hours']:.1f}")]
    pdf.set_font("DejaVu", "", 8.5)
    with pdf.table(col_widths=(45, 135), first_row_as_headings=False, line_height=4.6, text_align="LEFT") as t:
        for k, v in rows:
            row = t.row()
            row.cell(k, style=None)
            row.cell(str(v))
    if r.get("verdict_reason"):
        pdf.set_font("DejaVu", "", 7.5)
        pdf.multi_cell(0, 3.6, f"Auditor: {r['verdict_reason']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    pdf.image(io.BytesIO(auditor_chart(r.get("llr_trace", []))), w=120)
    pdf.ln(1)
    pdf.set_font("DejaVu", "B", 9)
    pdf.cell(0, 5, "Timeline", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 6.8)
    for e in r["timeline"]:
        prov = f" [{e['provider'].split(' (')[0]}]" if e.get("provider") else ""
        pdf.multi_cell(0, 3.1, f"{e['agent']}: {e['text']}{prov}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    pdf.set_font("DejaVu", "B", 9)
    pdf.cell(0, 5, "Evidence ledger", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 6.5)
    with pdf.table(col_widths=(24, 70, 14, 34, 38), line_height=3.0, text_align="LEFT") as t:
        head = t.row()
        for h in ("Dimension", "Finding", "Supports", "Reliability", "Source tool"):
            head.cell(h, style=None)
        for x in r["ledger"]:
            row = t.row()
            for v in (x["dimension"], x["finding"], x.get("supports", ""), x.get("reliability", ""), x.get("source", "")):
                row.cell(str(v))


def build_report(records: list[dict]) -> bytes:
    """A PDF with one section (starting on its own page) per case. Raises ValueError with no cases."""
    if not records:
        raise ValueError("no cases to report")
    pdf = _Pdf(format="A4")
    pdf.add_font("DejaVu", "", os.path.join(_FONTS, "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", os.path.join(_FONTS, "DejaVuSans-Bold.ttf"))
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(True, margin=12)
    pdf.set_margins(15, 12, 15)
    pdf.set_title("NEER case report")
    pdf.set_author("NEER")
    for r in records:
        _section(pdf, r)
    return bytes(pdf.output())
