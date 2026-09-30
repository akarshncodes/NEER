"""What "normal" looks like, learned only from certified-clean days.

Memory safety rules:
  * only history days or days the Auditor proved leak-free may be learned from,
  * never update after a single clean observation (need BASELINE_MIN_NEW_DAYS pending days),
  * rolling window of BASELINE_MAX_DAYS so seasonal / policy changes are learned gradually,
  * every update gets a new version number and timestamp (audit trail).
So a slowly growing leak can never become the new normal.
"""
from __future__ import annotations

import time

import numpy as np

from neer import config
from neer.sim.city import DayData


class Baseline:
    """Normal pressure and zone inflow for every hour, plus how noisy each one is."""

    def __init__(self, clean_days: list[DayData]) -> None:
        if len(clean_days) < 3:
            raise ValueError("Need at least 3 clean days to learn normal behaviour")
        self.days = list(clean_days)[-config.BASELINE_MAX_DAYS:]
        self.pending: list[DayData] = []
        self.version = 1
        self.updated_at = time.time()
        self.versions: list[dict] = [{"version": 1, "days": len(self.days), "at": self.updated_at, "why": "history"}]
        self._fit()

    # ------------------------------------------------------------ learning
    def _fit(self) -> None:
        P = np.stack([d.pressure for d in self.days])       # n x H x sensors
        Z = np.stack([d.zone_inflow for d in self.days])    # n x H x zones
        self.pn, self.ps = _mean_sd(P, config.PRESSURE_SD_FLOOR)
        self.zn, self.zs = _mean_sd(Z, config.FLOW_SD_FLOOR)
        # leave-one-out: how much does a normal day's "excess" and "score" wobble?
        ex, sc = [], []
        for k in range(len(self.days)):
            rest = [d for i, d in enumerate(self.days) if i != k]
            b = Baseline.__new__(Baseline)
            b.pn, b.ps = _mean_sd(np.stack([d.pressure for d in rest]), config.PRESSURE_SD_FLOOR)
            b.zn, b.zs = _mean_sd(np.stack([d.zone_inflow for d in rest]), config.FLOW_SD_FLOOR)
            ex.append(b.zone_excess([self.days[k]]))
            sc.append(b.pressure_score([self.days[k]]))
        self.ex_se = np.maximum(np.std(ex, axis=0, ddof=1), config.EX_SE_FLOOR) * config.EX_SE_INFLATE
        self.p_thr = float(np.max(sc)) * config.P_THR_INFLATE

    def add_certified_clean(self, day: DayData) -> bool:
        """The Auditor proved this day leak-free. It is queued; 'normal' is re-learned only once
        enough certified days are pending. Returns True if a new baseline version was created."""
        day.certified_clean = True
        if any(d.day == day.day for d in self.days + self.pending):
            return False
        self.pending.append(day)
        if len(self.pending) < config.BASELINE_MIN_NEW_DAYS:
            return False
        self.days = (self.days + self.pending)[-config.BASELINE_MAX_DAYS:]
        self.pending = []
        self.version += 1
        self.updated_at = time.time()
        self.versions.append({"version": self.version, "days": len(self.days), "at": self.updated_at,
                              "why": "auditor-certified clean days"})
        self._fit()
        return True

    def info(self) -> dict:
        return {"version": self.version, "clean_days": len(self.days), "pending_certified_days": len(self.pending),
                "updated_at": round(self.updated_at, 1)}

    # ------------------------------------------------------------ evidence 1: mass balance
    def zone_excess(self, days: list[DayData], hours: slice = slice(0, config.HOURS)) -> np.ndarray:
        """Unexplained extra water per zone (L/s). Quiet hours count more (weights 1/sd^2);
        a city-wide swing that lifts every zone (hot day, holiday) is removed."""
        z = np.mean([d.zone_inflow for d in days], axis=0)[hours]
        w = 1.0 / self.zs[hours] ** 2
        ex = ((z - self.zn[hours]) * w).sum(0) / w.sum(0)
        n = np.maximum(np.abs((self.zn[hours] * w).sum(0) / w.sum(0)), 1.0)
        return ex - np.median(ex / n) * n

    def zone_t(self, days: list[DayData], hours: slice = slice(0, config.HOURS), widen: float = 1.0) -> np.ndarray:
        """Excess divided by its normal wobble (more days of data -> smaller wobble)."""
        return self.zone_excess(days, hours) / (self.ex_se * widen / np.sqrt(len(days)))

    # ------------------------------------------------------------ evidence 2: hydraulic response
    def pressure_residual(self, days: list[DayData], masked: list[int] = ()) -> np.ndarray:
        """Normal minus observed pressure (positive = pressure dropped). Offline/masked sensors -> 0."""
        obs = np.mean([d.pressure for d in days], axis=0)
        r = self.pn - obs
        r = np.where(np.isnan(r), 0.0, r)
        if len(masked):
            r[:, list(masked)] = 0.0
        return r

    def pressure_z(self, days: list[DayData], masked: list[int] = ()) -> np.ndarray:
        return self.pressure_residual(days, masked) / self.ps

    def pressure_score(self, days: list[DayData], masked: list[int] = ()) -> float:
        z = self.pressure_z(days, masked)
        return float(np.sqrt((z ** 2).mean()))


def _mean_sd(x: np.ndarray, floor: float) -> tuple[np.ndarray, np.ndarray]:
    return np.nanmean(x, axis=0), np.maximum(np.nanstd(x, axis=0, ddof=1), floor)
