"""All NEER constants in one place.

Every number here was tested earlier (see reference/ and docs/SPEC.md).
Change a value here, never inside the code that uses it.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Read NEER/.env (KEY=value lines) into the environment, without overriding real env vars."""
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
LIBRARY_CACHE = CACHE_DIR / "fingerprints.npz"
# overridable by env so MCP server processes share the exact same files as their client
CASES_DB = Path(os.getenv("NEER_CASES_DB", DATA_DIR / "cases.db"))
TRACE_DB = Path(os.getenv("NEER_TRACE_DB", DATA_DIR / "trace.db"))
CHAOS_FILE = Path(os.getenv("NEER_CHAOS_FILE", DATA_DIR / "chaos.json"))
WORLD_FILE = Path(os.getenv("NEER_WORLD_FILE", DATA_DIR / "world.pkl"))


def use_private_runtime(name: str) -> None:
    """Give a batch job (evaluation, ablation) its own chaos / world / trace files under data/runs/<name>/.

    Without this, an evaluation running while the dashboard is open would share data/chaos.json and
    data/trace.db with it: the eval's chaos toggles would fire in the demo, and the demo's tool calls
    would be counted in the eval. Call it at the start of main(), before any tool runs.
    """
    global TRACE_DB, CHAOS_FILE, WORLD_FILE
    run_dir = DATA_DIR / "runs" / name
    run_dir.mkdir(parents=True, exist_ok=True)
    TRACE_DB, CHAOS_FILE, WORLD_FILE = run_dir / "trace.db", run_dir / "chaos.json", run_dir / "world.pkl"

# ---------------------------------------------------------------- network
HOURS = 24                      # one simulated day = 24 hourly values
N_ZONES = 5                     # District Metered Areas (DMAs)
HISTORY_DAYS = 7                # normal days a new city starts with
PUMP_ID = "10"                  # pump used in the pump-trip scenario

# 20 pressure sensors, chosen earlier for how well they tell leaks apart
PRESSURE_SENSORS = [
    "101", "211", "208", "40", "139", "117", "197", "15", "241", "10",
    "265", "103", "149", "229", "143", "217", "167", "219", "35", "207",
]
# big customers with their own smart meters (subtracted from zone inflow)
BULK_CUSTOMERS = ["203", "35", "123", "15"]
# pipes that can be closed without cutting off part of the network
SAFE_VALVES = ["107", "113", "115", "145", "147", "153", "163", "171", "186",
               "202", "223", "245", "269", "289", "305", "307", "311"]

# ---------------------------------------------------------------- realism (hidden noise)
DEMAND_BIAS_SD = 0.10           # each customer's use differs from the model by ~10 %
DEMAND_DAILY_SD = 0.03          # day-to-day variation per customer
DEMAND_HOURLY_SD = 0.03         # city-wide hour-to-hour variation (weather etc.)
PRESSURE_NOISE_M = 0.10         # pressure sensor noise, metres
METER_BIAS_SD = 0.02            # each flow meter reads up to ~2 % off (fixed)
METER_NOISE_SD = 0.01           # random flow-meter reading noise
BULK_NOISE_SD = 0.01            # bulk-meter reading noise

# ---------------------------------------------------------------- leak model
GRAVITY = 9.81
DISCHARGE_COEF = 0.75
REF_PRESSURE_M = 40.0           # pressure used to convert L/s <-> orifice area
LIB_SIZES_M2 = (0.0004, 0.0012, 0.003)   # fingerprint library leak sizes

# ---------------------------------------------------------------- engine (tested values)
PRESSURE_SD_FLOOR = 0.05        # m
FLOW_SD_FLOOR = 0.5             # L/s
EX_SE_INFLATE = 1.2             # safety factor on zone-excess spread
EX_SE_FLOOR = 0.3               # L/s
P_THR_INFLATE = 1.25            # safety factor on pressure-score threshold
Z_THR = 4.0                     # water witness: zone t-score threshold
LATE_HOURS = slice(18, 24)      # persistence witness window
LATE_T_THR = 2.5
HOT_Z = 2.5                     # "anomalous hour" threshold (pressure z-RMS)
HOT_FLOW_T = 4.0
TEMPER = 0.1                    # how strongly pressure fingerprints sharpen the map
FROZEN_SD = 0.01                # a sensor this flat is frozen
LONE_WOLF_Z = 4.0
LONE_WOLF_SECOND = 2.0

# search / field
SOFT_ACOUSTIC_NO = 0.15         # area weight after an acoustic "no"
SOFT_EMPTY_DIG = 0.10           # area weight after a dig found nothing
SOFT_NOT_FIXED = 1.00           # repaired area when the Auditor says NOT FIXED: the crew DID find leak signs there,
                                # so the site keeps its weight (most often a wrong pipe nearby)
ACOUSTIC_SENSITIVITY = 0.85
ACOUSTIC_FPR = 0.05
ACOUSTIC_INCONCLUSIVE = 0.05    # traffic noise / plastic pipe: the survey cannot decide
SURVEY_SETUP_H = 1.0            # crew-hours to set up an overnight acoustic survey
SURVEY_H_PER_KM = 1.0           # crew-hours per km of pipe walked
DIG_HOURS = 6.0                 # crew-hours for an excavation + repair
PLAN_MODE = os.getenv("NEER_PLAN_MODE", "fast")   # fast = find the leak soonest; cheap = save crew-hours
IG_WEIGHT = 0.3                 # information gain as tie-breaker in the next-best-action value
COST_WEIGHT = 0.0 if PLAN_MODE == "fast" else 0.2
MAX_REPLANS = 6
MIN_ACTIONABLE_LPS = 6.0        # smaller signals: wait for more days of data before sending anyone
MAX_WAIT_DAYS = 2
MAX_VISITS = 8

# auditor (sequential probability ratio test)
SPRT_ODDS = 99.0                # decide NOT FIXED / PARTLY at 99:1 evidence
SPRT_ODDS_FIXED = 999.0         # closing a case needs stronger proof (a wrong FIXED is the costly error)
SPRT_MIN_HOURS_FIXED = 3        # and at least 3 hours of data
SPRT_NOISE_INFLATE = 2.0
SPRT_MAX_HOURS = 72
PARTIAL_DROP = 0.35             # >35 % drop but still leaking -> PARTLY FIXED
UNHEALTHY_SENSOR_FRAC = 0.30

# baseline memory safety
BASELINE_MIN_NEW_DAYS = 2       # never update 'normal' from a single clean observation
BASELINE_MAX_DAYS = 14          # rolling window, so seasonal / policy changes are learned gradually

# safety: who may approve physical actions (role-based access control)
APPROVER_ROLES = ("supervisor", "engineer")

# ---------------------------------------------------------------- impact (ASSUMPTION, not measured)
COST_PER_M3_INR = 25            # assumed value of one cubic metre of treated water, in rupees. Shown as "at ₹25/m³ (assumption)".

# ---------------------------------------------------------------- LLM / tools
LLM_CHAIN = os.getenv(
    "NEER_LLM_CHAIN",
    "groq:openai/gpt-oss-120b,gemini:gemini-3.5-flash,ollama:qwen2.5:7b,rules",
)
LLM_TIMEOUT_S = 20
LLM_DOWN_AFTER = 2              # consecutive network failures (timeout, connection, 429, auth) before a provider rests
LLM_COOLDOWN_S = 60             # ...and it is skipped for this long, so bad Wi-Fi never makes a demo crawl
TOOL_MODE = os.getenv("NEER_TOOL_MODE", "direct")   # "direct" or "mcp"
TOOL_TIMEOUT_S = 10
TOOL_RETRIES = 2
BREAKER_FAILS = 3
BREAKER_COOLDOWN_S = 60
