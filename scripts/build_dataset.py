"""Build the NEER demo dataset (CSV files you can open in Excel) into dataset/.

    uv run python scripts/build_dataset.py

What it writes (all simulated from the public EPA Net3 network - not field data):
  dataset/network/        the city: junctions, pipes, pumps/tanks/sources, zones, meters, sensors, bulk customers
  dataset/live_city/      30 nights of the live city (seed 7): hourly SCADA pressure + zone inflow, ops log,
                          calendar, the 02:00-04:00 night-scan summary, and the hidden truth (judges only)
  dataset/scenarios/      one day of raw SCADA data for each of the 16 scripted test scenarios

Same seed -> same files, every time.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from neer import config  # noqa: E402
from neer.engine.baseline import Baseline  # noqa: E402
from neer.live import make_schedule  # noqa: E402
from neer.sim.city import SimCity  # noqa: E402
from neer.sim.network import get_network  # noqa: E402
from neer.sim.scenarios import SCENARIOS  # noqa: E402

OUT = ROOT / "dataset"
SEED = 7
NIGHTS = 30


def write(path: Path, header: list[str], rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)
            n += 1
    return n


def network_files() -> dict[str, int]:
    net = get_network()
    wn = net.wn
    zone = lambda n: net.zone_names[net.node_zone[n]] if net.node_zone.get(n, -1) >= 0 else "source/storage"  # noqa: E731
    out = {}
    out["network/junctions.csv"] = write(
        OUT / "network/junctions.csv", ["junction", "x", "y", "elevation_m", "zone", "is_pressure_sensor", "is_bulk_customer"],
        ([j, round(net.coords[j][0], 2), round(net.coords[j][1], 2), round(wn.get_node(j).elevation, 2), zone(j),
          int(j in net.sensors), int(j in config.BULK_CUSTOMERS)] for j in net.junctions))
    out["network/pipes.csv"] = write(
        OUT / "network/pipes.csv", ["pipe", "from_node", "to_node", "length_m", "diameter_m", "zone", "is_zone_meter"],
        ([p, wn.get_link(p).start_node_name, wn.get_link(p).end_node_name, round(wn.get_link(p).length, 1),
          round(wn.get_link(p).diameter, 3),
          zone(wn.get_link(p).start_node_name) if zone(wn.get_link(p).start_node_name) == zone(wn.get_link(p).end_node_name)
          else "border", int(p in net.meters)] for p in wn.pipe_name_list))
    out["network/sources_tanks_pumps.csv"] = write(
        OUT / "network/sources_tanks_pumps.csv", ["name", "type", "x", "y"],
        [[n, "reservoir (source)", *net.coords[n]] for n in wn.reservoir_name_list]
        + [[n, "tank", *net.coords[n]] for n in wn.tank_name_list]
        + [[p, "pump", "", ""] for p in wn.pump_name_list])
    out["network/zone_meters.csv"] = write(
        OUT / "network/zone_meters.csv", ["meter_on_link", "from_node", "to_node", "from_zone", "to_zone"],
        ([m, wn.get_link(m).start_node_name, wn.get_link(m).end_node_name, zone(wn.get_link(m).start_node_name),
          zone(wn.get_link(m).end_node_name)] for m in net.meters))
    out["network/zones.csv"] = write(
        OUT / "network/zones.csv", ["zone", "junctions", "pressure_sensors", "border_meters"],
        ([z, len(net.zone_junctions(z)), sum(1 for s in net.sensors if net.zone_of(s) == z),
          int((net.MZ[i] != 0).sum())] for i, z in enumerate(net.zone_names)))
    return out


def day_rows(d, net):
    for h in range(config.HOURS):
        yield [d.day, h, int(d.certified_clean)] + [None if np.isnan(x) else round(float(x), 3) for x in d.pressure[h]]


def live_city() -> dict[str, int]:
    """30 nights exactly as the night watch sees them (events start on their scheduled night)."""
    net = get_network()
    city = SimCity(SEED)                       # 7 certified-clean history days first
    base = Baseline(city.clean_history())
    schedule, reveal = make_schedule(SEED)
    first = city.day
    scans = []
    for night in range(1, NIGHTS + 1):
        for item in schedule.pop(night, []):
            if item == "misfix":
                continue                       # a field event (the crew's mistake), not visible in SCADA
            if isinstance(item, tuple):
                city.fix_sensor(item[1])
            else:
                city.add_event(item)
        d = city.advance_day()
        ex = base.zone_excess([d], config.NIGHT_HOURS)
        t = base.zone_t([d], config.NIGHT_HOURS, widen=2.0)
        obs = d.zone_inflow[config.NIGHT_HOURS].mean(0)
        for i, z in enumerate(net.zone_names):
            scans.append([night, d.day, z, round(float(obs[i]), 2), round(float(base.zn[config.NIGHT_HOURS, i].mean()), 2),
                          round(float(ex[i]), 2), round(float(t[i]), 2), int(t[i] > config.Z_THR)])
    days = city.history
    out = {}
    s_cols = [f"S{s}_m" for s in net.sensors]
    out["live_city/scada_pressure_hourly.csv"] = write(
        OUT / "live_city/scada_pressure_hourly.csv", ["day", "hour", "certified_clean_history"] + s_cols,
        (r for d in days for r in day_rows(d, net)))
    out["live_city/scada_zone_inflow_hourly.csv"] = write(
        OUT / "live_city/scada_zone_inflow_hourly.csv",
        ["day", "hour", "certified_clean_history"] + [f"{z}_net_inflow_lps" for z in net.zone_names],
        ([d.day, h, int(d.certified_clean)] + [round(float(x), 2) for x in d.zone_inflow[h]]
         for d in days for h in range(config.HOURS)))
    out["live_city/ops_log.csv"] = write(OUT / "live_city/ops_log.csv", ["day", "op_id", "kind", "detail"],
                                         ([o.day, o.op_id, o.kind, o.detail] for d in days for o in d.ops_log))
    out["live_city/supply_calendar.csv"] = write(OUT / "live_city/supply_calendar.csv", ["day", "entry_id", "zone", "detail"],
                                                 ([c.day, c.entry_id, c.zone, c.detail] for d in days for c in d.calendar))
    out["live_city/night_scan_0200_0400.csv"] = write(
        OUT / "live_city/night_scan_0200_0400.csv",
        ["night", "day", "zone", "night_inflow_lps", "normal_night_lps", "excess_lps", "t_score", "above_alarm_line"], scans)
    out["live_city/hidden_truth_JUDGES_ONLY.csv"] = write(
        OUT / "live_city/hidden_truth_JUDGES_ONLY.csv", ["night", "day", "hidden_event"],
        ([r["night"], first + r["night"] - 1, r["event"]] for r in reveal))
    return out


def scenarios() -> dict[str, int]:
    net = get_network()
    out = {}
    for name, sc in SCENARIOS.items():
        city = SimCity(SEED)
        for e in sc.events:
            city.add_event(e)
        d = city.advance_day()
        rows = ([h] + [round(float(x), 3) if not np.isnan(x) else None for x in d.pressure[h]]
                + [round(float(x), 2) for x in d.zone_inflow[h]] for h in range(config.HOURS))
        out[f"scenarios/{name}.csv"] = write(
            OUT / f"scenarios/{name}.csv",
            ["hour"] + [f"S{s}_m" for s in net.sensors] + [f"{z}_inflow_lps" for z in net.zone_names], rows)
    return out


def main() -> None:
    counts = {**network_files(), **live_city(), **scenarios()}
    write(OUT / "MANIFEST.csv", ["file", "rows"], sorted(counts.items()))
    total = sum(counts.values())
    print(f"dataset/: {len(counts)} files, {total:,} rows")


if __name__ == "__main__":
    main()
