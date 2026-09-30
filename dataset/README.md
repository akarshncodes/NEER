# NEER demo dataset

Everything NEER's demo runs on, as plain CSV files you can open in Excel.
Rebuild it at any time with `uv run python scripts/build_dataset.py`. The same seed (7) always gives the same files.

## Where the data comes from (say this first)
- **The network is real and public:** **EPA Net3**, a benchmark water network published by the US Environmental Protection Agency. It ships with EPANET and WNTR and is used in hundreds of research papers.
  - 92 junctions and 117 pipes
  - 2 sources (a river and a lake), 3 tanks, 2 pumps
- **The readings are simulated:** we have no utility SCADA data, so NEER's pretend city runs the network in **WNTR / EPANET** (the EPA's hydraulic simulator), hour by hour. Hidden realism is added:
  - each consumer's use differs ±10% from the model
  - use varies ±3% day to day and hour to hour
  - pressure sensors are ±0.1 m off
  - meters have a fixed 2% bias plus 1% reading noise
- **The events are injected:** leaks, a pump trip, planned flushing, fire-fighting, a stuck sensor and a valve closure, each at a known place and time. That's how we can score NEER: we know the right answer and NEER doesn't.
- **Not field data.** The next step is the public **BattLeDIM L-Town** dataset, then a utility's historical data, then a one-DMA pilot.

## Folders
| Folder / file | Rows | What it is |
|---|---|---|
| `network/junctions.csv` | 92 | junction id, x/y, elevation (m), zone, whether it has a pressure sensor, whether it is a bulk-metered customer |
| `network/pipes.csv` | 117 | pipe id, from/to node, length (m), diameter (m), zone ("border" = crosses zones), whether it carries a zone meter |
| `network/sources_tanks_pumps.csv` | 7 | the 2 sources, 3 tanks and 2 pumps |
| `network/zone_meters.csv` | 15 | the 15 flow meters on pipes crossing zone borders, and which zones they connect |
| `network/zones.csv` | 5 | zones Z1–Z5 (DMAs): junctions, sensors and border meters |
| `live_city/scada_pressure_hourly.csv` | 888 | **raw SCADA pressure**: 37 days × 24 h × 20 sensors (m). The first 7 days are certified-clean history |
| `live_city/scada_zone_inflow_hourly.csv` | 888 | **raw zone inflow** per hour (L/s), net of the 4 bulk-metered customers |
| `live_city/ops_log.csv` | – | operator actions SCADA logged (pump trip, valve closure) |
| `live_city/supply_calendar.csv` | – | planned work (flushing / tanker filling) |
| `live_city/night_scan_0200_0400.csv` | 150 | what the Sentinel computes every night for each zone: 02:00–04:00 inflow vs normal, excess L/s, t-score, above the alarm line or not |
| `live_city/hidden_truth_JUDGES_ONLY.csv` | 10 | the hidden events and the night each starts (NEER never reads this file) |
| `scenarios/<name>.csv` | 24 each | one day of raw pressure + zone inflow for each of the 16 scripted test scenarios |
| `MANIFEST.csv` | – | every file with its row count |

The live-city files show the city **without** NEER acting (leaks keep running), so you can find each hidden event in the raw numbers yourself.

## A 30-second check anyone can do in Excel
1. Open `live_city/night_scan_0200_0400.csv` and filter `night = 2`. Zone **Z1** takes 22.0 L/s at night against a normal 7.2 L/s (excess ≈ 15 L/s after removing the city-wide swing). The hidden 20 L/s leak at junction 275 started that night.
2. Open `live_city/scada_zone_inflow_hourly.csv`. From day 8 on, `Z1_net_inflow_lps` at 02:00–04:00 sits about 15–20 L/s above the history days (about 7 L/s).
3. Open `hidden_truth_JUDGES_ONLY.csv`: night 2 is "leak: node 275, lps 20".

## Column units
- pressure: metres of water head (m)
- flow: litres per second (L/s)
- length: metres
- diameter: metres
- hour: 0–23
- day: simulation day number
- **t-score:** extra water ÷ its normal day-to-day wobble. Above 4 is the alarm line.
