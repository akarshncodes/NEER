"""Export the simulated SCADA dataset to CSV files so it can be opened in Excel.

    uv run python scripts/export_dataset.py            # scenario leak_20, seed 7
    uv run python scripts/export_dataset.py pump_trip 7

Writes data/export/<scenario>/:
  pressure.csv      one row per hour: day, hour, 20 pressure sensors (m)
  zone_inflow.csv   one row per hour: day, hour, 5 zones (L/s, net of bulk meters)
  events.csv        ops log + calendar entries (what SCADA logged)
  hidden_truth.csv  the injected events NEER never sees (for checking only)
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from neer.sim.city import SimCity
from neer.sim.scenarios import SCENARIOS


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "leak_20"
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    sc = SCENARIOS[name]
    city = SimCity(seed=seed)                       # 7 certified-clean history days
    for e in sc.events:
        city.add_event(e)
    for _ in range(sc.days_before_case):            # days with the problem running
        city.advance_day()

    out = Path("data/export") / name
    out.mkdir(parents=True, exist_ok=True)
    net = city.net

    with open(out / "pressure.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["day", "hour", "clean_history"] + [f"S{s}_m" for s in net.sensors])
        for d in city.history:
            for h in range(d.pressure.shape[0]):
                w.writerow([d.day, h, d.certified_clean] + [round(float(x), 3) for x in d.pressure[h]])

    with open(out / "zone_inflow.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["day", "hour", "clean_history"] + [f"{z}_lps" for z in net.zone_names])
        for d in city.history:
            for h in range(d.zone_inflow.shape[0]):
                w.writerow([d.day, h, d.certified_clean] + [round(float(x), 2) for x in d.zone_inflow[h]])

    with open(out / "events.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["day", "source", "id", "detail"])
        for d in city.history:
            for o in d.ops_log:
                w.writerow([d.day, "ops_log", o.op_id, o.detail])
            for c in d.calendar:
                w.writerow([d.day, "calendar", c.entry_id, c.detail])

    with open(out / "hidden_truth.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "event"])
        for e in sc.events:
            w.writerow([name, e.model_dump_json()])

    days = len(city.history)
    print(f"Exported {days} days x 24 h for '{name}' (seed {seed}) to {out}/")
    print(f"  pressure.csv: {days * 24} rows x {len(net.sensors)} sensors")
    print(f"  zone_inflow.csv: {days * 24} rows x {len(net.zone_names)} zones")


if __name__ == "__main__":
    main()
