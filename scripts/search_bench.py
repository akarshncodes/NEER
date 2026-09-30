"""Larger search benchmark (120 leaks per size) - the headline 'found within N visits' numbers.

The 40-case rows in engine_report.py swing by about +/-7 % from sample to sample, so the
pitch quotes this bigger run instead.   uv run python scripts/search_bench.py [n]
"""
import sys

import neer.engine.bench as B

n = int(sys.argv[1]) if len(sys.argv) > 1 else 120
for lps in (10, 20, 40):
    r = B.search_run(lps, n, seed0=900)
    print(f"{lps:>3} L/s  zone {r['zone_correct']:.0%}  found<=3 visits {r['found_within_3']:.0%}  "
          f"found<=8 visits {r['found_within_6']:.0%}  wasted digs/leak {r['wasted_digs_per_leak']:.2f}  "
          f"top-area likelihood {r['top_likelihood_mean']:.0%} vs real hit {r['top_area_hit_rate']:.0%}")
