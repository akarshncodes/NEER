"""Print the engine's benchmark table (seeded, simulated). Quote only these numbers.

    uv run python scripts/engine_report.py [n]      (default n = 40 cases per row)
"""
import sys
import time

from rich.console import Console
from rich.table import Table

from neer.engine import bench as B

n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
con = Console()
t0 = time.time()

tab = Table(title=f"NEER physics engine - simulated Net3, {n} cases per row")
tab.add_column("Test"); tab.add_column("Result", justify="right")
tab.add_row("False alarms on leak-free days", f"{B.false_alarm_rate(n):.0%}")
for q in (10, 20, 40):
    tab.add_row(f"Detected on day 1 ({q} L/s)", f"{B.detection_rate(n, q):.0%}")
for k in B.SKEPTIC_SCENARIOS:
    r = B.skeptic_accuracy(k, n)
    tab.add_row(f"Skeptic correct: {k}", f"{r['correct']:.0%}  {r['verdicts']}")
for q in (10, 20, 40):
    r = B.search_run(q, n)
    tab.add_row(f"Search {q} L/s: zone / found<=3 visits / wasted digs",
                f"{r['zone_correct']:.0%} / {r['found_within_3']:.0%} / {r['wasted_digs_per_leak']:.2f}")
for q in (10, 20, 40):
    for case in ("fixed", "not_fixed", "partly"):
        r = B.audit_run(q, case, n)
        tab.add_row(f"Auditor {q} L/s {case}: correct / median h",
                    f"{r['correct']:.0%} / {r['median_hours']} h (never wrongly FIXED {r['never_wrongly_fixed']:.0%})")
con.print(tab)
con.print(f"[dim]took {time.time() - t0:.0f} s[/dim]")
