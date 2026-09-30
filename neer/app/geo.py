"""Map geometry for the Control Room: Net3 coordinates -> Madurai lat/lon, hulls, and a tile check.

The placement is ILLUSTRATIVE: EPA Net3 is an American test network, scaled and shifted onto a Madurai basemap.
"""
from __future__ import annotations

import math
import urllib.request

import numpy as np
from scipy.spatial import ConvexHull

CENTRE_LAT, CENTRE_LON = 9.925, 78.12          # Madurai
TARGET_KM = (4.0, 3.0)                          # the network covers about this much ground (east-west, north-south)
_M_PER_DEG_LAT = 111_320.0
_M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(CENTRE_LAT))


def _scale_shift(xy: np.ndarray) -> tuple[float, np.ndarray]:
    """One uniform scale (metres per Net3 unit, so the shape is not distorted) and the Net3 centre."""
    lo, hi = xy.min(0), xy.max(0)
    span = np.maximum(hi - lo, 1e-9)
    metres_per_unit = min(TARGET_KM[0] * 1000 / span[0], TARGET_KM[1] * 1000 / span[1])
    return metres_per_unit, (lo + hi) / 2


def to_latlon(xy: np.ndarray, reference: np.ndarray | None = None) -> np.ndarray:
    """Convert Net3 (x, y) to (lat, lon). `reference` = all network points, used to fit scale and shift.

    Simple scale-and-shift: the network centre lands on Madurai and its extent on about 4 km x 3 km.
    """
    xy = np.atleast_2d(np.asarray(xy, dtype=float))
    ref = xy if reference is None else np.atleast_2d(np.asarray(reference, dtype=float))
    scale, centre = _scale_shift(ref)
    east_m, north_m = (xy - centre).T * scale
    return np.column_stack([CENTRE_LAT + north_m / _M_PER_DEG_LAT, CENTRE_LON + east_m / _M_PER_DEG_LON])


def rounded_hull(points: np.ndarray, pad: float, n: int = 10) -> np.ndarray:
    """Convex hull of `points` grown by `pad` (same units): hull of a small circle around every point. Closed ring."""
    pts = np.atleast_2d(points)
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring = np.concatenate([p + pad * np.column_stack([np.cos(t), np.sin(t)]) for p in pts])
    hull = ring[ConvexHull(ring).vertices]
    return np.vstack([hull, hull[:1]])


def dashed(a: np.ndarray, b: np.ndarray, pieces: int = 7) -> list[tuple[np.ndarray, np.ndarray]]:
    """Split the segment a-b into short drawn pieces with gaps (for map layers that have no dash style)."""
    ts = np.linspace(0, 1, pieces * 2 + 1)
    return [(a + (b - a) * ts[i], a + (b - a) * ts[i + 1]) for i in range(0, len(ts) - 1, 2)]


_tiles_ok: dict[str, float | bool] = {}


def tiles_available(timeout: float = 5.0, ttl: float = 120.0, retry_after: float = 15.0) -> bool:
    """Can this machine reach the OpenStreetMap tile server? A success is cached for `ttl` s, a failure for `retry_after` s."""
    import time
    now = time.time()
    if "at" in _tiles_ok and now - _tiles_ok["at"] < (ttl if _tiles_ok["ok"] else retry_after):
        return bool(_tiles_ok["ok"])
    try:
        req = urllib.request.Request("https://tile.openstreetmap.org/0/0/0.png", headers={"User-Agent": "NEER-dashboard"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ok = r.status == 200
    except Exception:  # noqa: BLE001 - any failure means: use the schematic
        ok = False
    _tiles_ok.update(at=now, ok=ok)
    return ok
