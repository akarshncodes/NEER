"""Auditor maths: prove a repair from meter data, hour by hour (sequential test).

After the repair, how much of the leak is still there?  We compare three
hypotheses about the remaining fraction r of the pre-repair excess:
    r = 0 (FIXED)   r = 0.5 (PARTLY FIXED)   r = 1 (NOT FIXED)
Every hour adds evidence (Gaussian log-likelihood with inflated meter noise).
We stop as soon as one hypothesis beats both others by 99:1, or give
INCONCLUSIVE after 72 hours or if the data is unhealthy.
The Auditor never reads the crew's report - only meters.
"""
from __future__ import annotations

import numpy as np

from neer import config
from neer.engine.baseline import Baseline
from neer.schemas import AuditKind, AuditVerdict
from neer.sim.city import DayData

HYPOTHESES = (0.0, 0.5, 1.0)
VERDICTS = (AuditKind.fixed, AuditKind.partly_fixed, AuditKind.not_fixed)


def sequential_verify(b: Baseline, after_days: list[DayData], zone_idx: int, pre_excess: float,
                      unhealthy_sensor_frac: float = 0.0, max_hours: int = config.SPRT_MAX_HOURS) -> AuditVerdict:
    q = max(pre_excess, 1.0)
    thr = np.log(config.SPRT_ODDS)
    ll = np.zeros(len(HYPOTHESES))
    trace: list[float] = []
    errors: list[float] = []

    if unhealthy_sensor_frac >= config.UNHEALTHY_SENSOR_FRAC:
        return AuditVerdict(verdict=AuditKind.inconclusive, hours_used=0, llr_trace=[], pre_excess_lps=q,
                            post_excess_lps=float("nan"), reason="Too many unhealthy sensors to judge the repair.")
    hours = 0
    for d in after_days:
        for h in range(config.HOURS):
            e = d.zone_inflow[h, zone_idx] - b.zn[h, zone_idx]
            if np.isnan(e):
                continue
            s = b.zs[h, zone_idx] * config.SPRT_NOISE_INFLATE
            ll += -0.5 * ((e - np.array(HYPOTHESES) * q) / s) ** 2
            errors.append(e)
            hours += 1
            best = int(np.argmax(ll))
            margin = ll[best] - np.max(np.delete(ll, best))
            # meter for the dashboard: evidence for "leak still there" vs "fixed"
            trace.append(float(np.clip(ll[2] - ll[0], -thr * 1.5, thr * 1.5)))
            need = np.log(config.SPRT_ODDS_FIXED) if best == 0 else thr
            if margin > need and (best != 0 or hours >= config.SPRT_MIN_HOURS_FIXED):
                post = float(np.mean(errors))
                return AuditVerdict(verdict=VERDICTS[best], hours_used=hours, llr_trace=trace, pre_excess_lps=round(q, 2),
                                    post_excess_lps=round(post, 2), reason=_reason(VERDICTS[best], q, post, hours))
            if hours >= max_hours:
                break
        if hours >= max_hours:
            break
    post = float(np.mean(errors)) if errors else float("nan")
    return AuditVerdict(verdict=AuditKind.inconclusive, hours_used=hours, llr_trace=trace, pre_excess_lps=round(q, 2),
                        post_excess_lps=round(post, 2),
                        reason=f"Evidence still unclear after {hours} h; keep watching.")


def _reason(v: AuditKind, pre: float, post: float, hours: int) -> str:
    if v == AuditKind.fixed:
        return f"Zone inflow back to normal: {pre:.1f} -> {post:.1f} L/s extra, proven in {hours} h."
    if v == AuditKind.partly_fixed:
        return f"Loss dropped {pre:.1f} -> {post:.1f} L/s but not to normal: probably a second leak ({hours} h)."
    return f"No real change: {pre:.1f} -> {post:.1f} L/s extra after {hours} h. The leak is still there."
