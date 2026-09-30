"""What "normal" looks like, learned only from certified-clean days.

A day is certified clean if it is history, or if the Auditor proved the
network was leak-free that day. So a slowly growing leak can never become
the new normal.
"""
from __future__ import annotations

import numpy as np

from neer import config
from neer.sim.city import DayData


class Baseline:
    """Normal pressure and zone inflow for every hour, plus how noisy each one is."""

    def __init__(self, clean_days: list[DayData]) -> None:
        if len(clean_days) < 3:
            raise ValueError("Need at least 3 clean days to learn normal behaviour")
        self.days = list(clean_days)
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

    def add_certified_clean(self, day: DayData) -> None:
        """The Auditor proved this day leak-free: learn from it."""
        day.certified_clean = True
        self.days.append(day)
        self._fit()

    # ------------------------------------------------------------ water witness
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

    # ------------------------------------------------------------ pressure witness
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
