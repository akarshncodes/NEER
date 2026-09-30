"""Design tokens and the stylesheet for the Control Room (display only).

One accent (water blue) on cool neutrals, in a light and a dark set. Semantic colours (good / bad / warn) mean
state, never decoration. Shape rule: containers and controls use one 8 px radius, chips and tags are pills.
The fonts (Geist, Geist Mono) are self-hosted in `neer/app/static`.
"""
from __future__ import annotations

LIGHT = dict(
    name="light", bg="#f6f7f9", surface="#ffffff", surface2="#f1f3f6", line="#e2e6ec", line2="#c7cdd6",
    ink="#10151c", muted="#566170", faint="#8892a0",
    accent="#1f5fae", accent_soft="#e7f0fb", accent_ink="#173f73",
    good="#177a48", good_soft="#e5f4ec", bad="#be3a2d", bad_soft="#fbeceb", warn="#a35a00", warn_soft="#fdf0df",
    run="#d9622b", run_soft="#fdeee6", plot_fill="rgba(31,95,174,0.10)",
)
DARK = dict(
    name="dark", bg="#0d1117", surface="#151b23", surface2="#1c232d", line="#283140", line2="#3a4556",
    ink="#e7ebf0", muted="#9aa5b4", faint="#6f7b8b",
    accent="#5fa2ec", accent_soft="#14283f", accent_ink="#a9cdf6",
    good="#46b479", good_soft="#12291d", bad="#ef7a70", bad_soft="#331a1a", warn="#e0a04a", warn_soft="#33260f",
    run="#ef8a52", run_soft="#35200f", plot_fill="rgba(95,162,236,0.16)",
)

_current = dict(LIGHT)


def set_theme(name: str) -> dict:
    """Switch the tokens the figures and the stylesheet read. Called once per run from the dashboard."""
    _current.clear()
    _current.update(DARK if name == "dark" else LIGHT)
    return _current


def T() -> dict:
    """The active token set."""
    return _current


FONT_FACES = """
@font-face{font-family:'Geist';src:url('/app/static/Geist.woff2') format('woff2');font-weight:100 900;font-display:swap}
@font-face{font-family:'Geist Mono';src:url('/app/static/GeistMono.woff2') format('woff2');font-weight:100 900;font-display:swap}
"""


def css(t: dict | None = None) -> str:
    """The stylesheet for the HTML pieces (KPI strip, timeline, cards, ledger, board, legend)."""
    t = t or _current
    return f"""<style>{FONT_FACES}
:root{{--bg:{t['bg']};--surface:{t['surface']};--surface2:{t['surface2']};--line:{t['line']};--line2:{t['line2']};
--ink:{t['ink']};--muted:{t['muted']};--faint:{t['faint']};--accent:{t['accent']};--accent-soft:{t['accent_soft']};
--accent-ink:{t['accent_ink']};--good:{t['good']};--good-soft:{t['good_soft']};--bad:{t['bad']};--bad-soft:{t['bad_soft']};
--warn:{t['warn']};--warn-soft:{t['warn_soft']};--run:{t['run']};--run-soft:{t['run_soft']};--r:8px;
--mono:'Geist Mono',ui-monospace,SFMono-Regular,Menlo,monospace}}
.block-container{{padding-top:1.6rem;padding-bottom:2rem;max-width:1560px}}
h1{{font-size:1.75rem !important;letter-spacing:-.025em;font-weight:650 !important}}
h5,h4{{letter-spacing:-.01em}}
[data-testid="stSidebar"] h4{{font-size:.78rem;color:var(--muted);font-weight:600;margin:1.1rem 0 .2rem}}
[data-baseweb="tab-list"]{{gap:1.4rem;border-bottom:1px solid var(--line)}}
[data-baseweb="tab"]{{padding-left:0;padding-right:0}}

.pagehead{{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:.2rem}}
.pagehead .title{{font-size:1.75rem;font-weight:650;letter-spacing:-.025em;color:var(--ink)}}
.pagehead .tag{{font-size:.82rem;color:var(--muted)}}
.brand{{font-size:1.3rem;font-weight:700;letter-spacing:-.03em;color:var(--ink);line-height:1.1}}
.brand-sub{{font-size:.76rem;color:var(--muted);margin-top:2px}}
.kstrip{{display:grid;border:1px solid var(--line);
  border-radius:var(--r);background:var(--surface);margin:.7rem 0 1rem;overflow:hidden}}
.kcell{{padding:11px 14px;border-left:1px solid var(--line);min-width:0}}
.kcell:first-child{{border-left:0}}
@media (max-width:1100px){{.kstrip{{grid-template-columns:repeat(3,1fr) !important}}.kcell{{border-top:1px solid var(--line)}}}}
.kcell .v{{font-family:var(--mono);font-size:1.3rem;font-weight:600;color:var(--ink);letter-spacing:-.02em;line-height:1.15}}
.kcell .l{{font-size:.72rem;color:var(--muted);margin-top:3px;line-height:1.3}}
.kcell.hl .v{{color:var(--accent)}}

.chips{{display:flex;gap:8px;flex-wrap:wrap;margin:.2rem 0 .9rem}}
.badge{{display:inline-block;border-radius:999px;padding:3px 12px;font-weight:600;font-size:.76rem;border:1px solid var(--line);
  background:var(--surface);color:var(--ink)}}
.badge.state{{color:#fff;border-color:transparent}}
.badge.soft{{background:var(--accent-soft);color:var(--accent-ink);border-color:transparent}}
.badge.good{{background:var(--good-soft);color:var(--good);border-color:transparent}}

.tlwrap{{max-height:540px;overflow-y:auto;padding-right:4px}}
.tl{{display:flex;gap:10px;align-items:flex-start;padding:8px 6px;border-bottom:1px solid var(--line);font-size:.84rem;line-height:1.4}}
.tl .ag{{color:#fff;border-radius:999px;padding:1px 9px;font-size:.7rem;font-weight:650;white-space:nowrap;margin-top:1px}}
.tl .tx{{flex:1;color:var(--ink)}}
.tl .prov{{font-size:.66rem;color:var(--faint);white-space:nowrap;font-family:var(--mono)}}
.tl.verdict{{background:var(--good-soft)}}.tl.alert{{background:var(--bad-soft)}}.tl.human{{background:var(--warn-soft)}}
.tx .bd{{margin-top:5px}}
.bdg{{display:inline-block;border-radius:999px;padding:1px 8px;margin-right:5px;font-size:.68rem;font-weight:650;border:1px solid}}
.bdg.ai{{background:var(--accent-soft);color:var(--accent-ink);border-color:transparent}}
.bdg.rules{{background:var(--surface2);color:var(--muted);border-color:var(--line)}}
.bdg.ok{{background:var(--good-soft);color:var(--good);border-color:transparent}}
.bdg.veto{{background:var(--bad-soft);color:var(--bad);border-color:transparent}}

.card{{font-family:var(--mono);font-size:.78rem;line-height:1.6;border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:var(--r);padding:11px 14px;background:var(--surface);color:var(--ink)}}
.approve{{border:1px solid var(--warn);background:var(--warn-soft);border-radius:var(--r);padding:11px 14px;margin-bottom:8px;color:var(--ink)}}
.maplegend{{display:flex;gap:10px;align-items:center;font-size:.62rem;color:var(--muted);white-space:nowrap;overflow:hidden;margin-top:4px}}
.maplegend i{{display:inline-block;vertical-align:middle;margin-right:3px}}

.cards{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}}
.dc{{border:1px solid var(--line);border-top:3px solid var(--line2);border-radius:var(--r);padding:9px 11px;background:var(--surface);min-height:134px}}
.dc.idle{{background:var(--surface2);color:var(--faint)}}
.dch{{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:4px}}
.dch .ag{{color:#fff;border-radius:999px;padding:1px 9px;font-size:.7rem;font-weight:650}}
.dcc{{font-weight:650;font-size:.86rem;color:var(--ink);margin:2px 0}}
.dcr{{font-size:.75rem;line-height:1.35;color:var(--ink);opacity:.86;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}}
.dcf{{font-size:.67rem;color:var(--muted);margin-top:4px;line-height:1.35}}

.ledgerwrap{{max-height:450px;overflow:auto;border:1px solid var(--line);border-radius:var(--r);background:var(--surface)}}
table.ledger{{border-collapse:collapse;width:100%;font-size:.78rem}}
table.ledger th{{position:sticky;top:0;background:var(--surface2);text-align:left;padding:7px 10px;font-size:.72rem;color:var(--muted);font-weight:600;border-bottom:1px solid var(--line)}}
table.ledger td{{padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top;color:var(--ink)}}
table.ledger tr:last-child td{{border-bottom:0}}
table.ledger td.w,table.ledger td.src{{white-space:nowrap;color:var(--muted);font-family:var(--mono);font-size:.72rem}}
table.ledger td.d{{font-weight:600;white-space:nowrap}}
table.ledger td.rel{{color:var(--muted);font-size:.72rem}}
.chip{{display:inline-block;border-radius:999px;padding:1px 9px;font-weight:650;font-size:.7rem;white-space:nowrap}}
.chip-leak{{background:var(--bad-soft);color:var(--bad)}}
.chip-against{{background:var(--good-soft);color:var(--good)}}
.chip-neutral{{background:var(--surface2);color:var(--muted)}}
.chip-fixed{{background:var(--good);color:#fff}}
.chip-veto{{background:transparent;color:var(--bad);border:1px dashed var(--bad)}}

.kcol{{background:var(--surface2);border-radius:var(--r);padding:9px;min-height:130px}}
.khead{{font-weight:650;font-size:.8rem;color:var(--ink);margin-bottom:7px;display:flex;justify-content:space-between;align-items:center}}
.kcount{{background:var(--line);color:var(--muted);border-radius:999px;padding:0 8px;font-size:.7rem;font-family:var(--mono)}}
.kcard{{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:8px 10px;margin-bottom:7px}}
.kcard.kactive{{border:1.5px solid var(--accent)}}
.kid{{font-weight:650;font-size:.76rem;display:flex;justify-content:space-between;gap:4px;align-items:center;font-family:var(--mono)}}
.kmeta{{font-size:.72rem;color:var(--muted);line-height:1.4}}
.kempty{{font-size:.72rem;color:var(--faint);text-align:center;padding:12px 0}}
.vchip{{border-radius:999px;padding:0 8px;font-size:.64rem;font-weight:650;white-space:nowrap;font-family:var(--mono)}}
.vc-fixed{{background:var(--good-soft);color:var(--good)}}
.vc-bad{{background:var(--bad-soft);color:var(--bad)}}
.vc-none{{background:var(--surface2);color:var(--muted)}}
.vc-open{{background:var(--accent-soft);color:var(--accent-ink)}}
</style>"""


CSS = css(LIGHT)
