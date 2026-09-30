"""Presentation layer: the animated pieces of the Control Room (pure HTML + CSS, no extra libraries).

- hero()            animated water banner with a live pulse, the one-line pitch and live counters
- mission()         the SUSPECT -> QUESTION -> INVESTIGATE -> ACT -> VERIFY -> REPLAN stepper; the current
                    stage glows, finished stages fill in, re-plans show as a loop counter
- outcome()         the end-of-case banner: FIXED (with animated water / money counters), escalated or dismissed
- toast_for()       short pop-up notifications for the key moments while the agents run

Everything shown is read from the case state and the world's KPIs - nothing here invents a number.
"""
from __future__ import annotations

from neer import config

CSS = """<style>
@property --n{syntax:'<integer>';initial-value:0;inherits:false}
.hero{position:relative;overflow:hidden;border-radius:14px;padding:18px 22px 20px;margin:0 0 .6rem;
  background:linear-gradient(120deg,#0b3a66 0%,#0f5c99 45%,#1386b8 100%);color:#fff;box-shadow:0 8px 28px rgba(11,58,102,.25)}
.hero .row{position:relative;z-index:2;display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.hero .logo{font-size:2rem;font-weight:800;letter-spacing:-.04em;line-height:1}
.hero .logo small{font-weight:300;opacity:.85;margin-left:6px;font-size:1.3rem}
.hero .pitch{font-size:.9rem;opacity:.95;max-width:720px;line-height:1.35}
.hero .live{display:inline-flex;align-items:center;gap:7px;font-size:.72rem;font-weight:700;letter-spacing:.08em;
  background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.3);border-radius:999px;padding:3px 10px}
.hero .dot{width:8px;height:8px;border-radius:50%;background:#4ade80;box-shadow:0 0 0 0 rgba(74,222,128,.7);
  animation:ping 1.6s infinite}
@keyframes ping{0%{box-shadow:0 0 0 0 rgba(74,222,128,.7)}70%{box-shadow:0 0 0 10px rgba(74,222,128,0)}100%{box-shadow:0 0 0 0 rgba(74,222,128,0)}}
.hero .stats{margin-left:auto;display:flex;gap:22px}
.hero .stat .v{font-family:var(--mono);font-size:1.35rem;font-weight:700;line-height:1}
.hero .stat .l{font-size:.66rem;opacity:.8;margin-top:3px;text-transform:uppercase;letter-spacing:.06em}
.hero svg.wave{position:absolute;left:0;bottom:-2px;width:200%;height:56px;z-index:1;opacity:.28;animation:drift 9s linear infinite}
.hero svg.wave.w2{opacity:.18;animation-duration:14s;animation-direction:reverse;height:70px}
@keyframes drift{from{transform:translateX(0)}to{transform:translateX(-50%)}}
.hero .drop{position:absolute;right:36%;top:-12px;width:10px;height:14px;border-radius:50% 50% 50% 50%/60% 60% 40% 40%;
  background:rgba(255,255,255,.55);animation:fall 3.2s ease-in infinite;z-index:1}
.hero .drop.d2{right:22%;animation-delay:1.1s}.hero .drop.d3{right:58%;animation-delay:2.2s}
@keyframes fall{0%{transform:translateY(0);opacity:0}15%{opacity:1}100%{transform:translateY(120px);opacity:0}}

.mission{display:grid;grid-template-columns:repeat(6,1fr);gap:0;margin:.3rem 0 1rem;position:relative}
.mstep{position:relative;text-align:center;padding:0 4px}
.mstep .bar{position:absolute;top:17px;left:-50%;width:100%;height:4px;background:var(--line);z-index:0}
.mstep:first-child .bar{display:none}
.mstep.done .bar,.mstep.now .bar{background:linear-gradient(90deg,var(--accent),var(--accent));background-size:200% 100%}
.mstep.now .bar{background:linear-gradient(90deg,var(--accent) 0%,#7dd3fc 50%,var(--accent) 100%);background-size:200% 100%;
  animation:flow 1.4s linear infinite}
@keyframes flow{from{background-position:200% 0}to{background-position:0 0}}
.mstep .ball{position:relative;z-index:1;width:38px;height:38px;margin:0 auto;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-weight:800;font-size:.82rem;background:var(--surface);border:2px solid var(--line);color:var(--faint)}
.mstep.done .ball{background:var(--accent);border-color:var(--accent);color:#fff}
.mstep.now .ball{background:var(--accent);border-color:var(--accent);color:#fff;animation:glow 1.5s ease-in-out infinite}
.mstep.good .ball{background:var(--good);border-color:var(--good)}
.mstep.bad .ball{background:var(--bad);border-color:var(--bad)}
@keyframes glow{0%,100%{box-shadow:0 0 0 0 rgba(37,99,235,.55)}50%{box-shadow:0 0 0 9px rgba(37,99,235,0)}}
.mstep .name{font-size:.72rem;font-weight:750;letter-spacing:.06em;margin-top:6px;color:var(--ink)}
.mstep .who{font-size:.66rem;color:var(--muted)}
.mstep .loop{display:inline-block;margin-top:2px;font-size:.62rem;font-weight:700;color:var(--warn);font-family:var(--mono)}

.outcome{position:relative;overflow:hidden;border-radius:12px;padding:16px 20px;margin:0 0 1rem;display:flex;
  align-items:center;gap:22px;flex-wrap:wrap;animation:rise .7s cubic-bezier(.2,.8,.2,1) both}
@keyframes rise{from{transform:translateY(12px) scale(.98);opacity:0}to{transform:none;opacity:1}}
.outcome.fixed{background:linear-gradient(110deg,#065f46,#059669 60%,#10b981);color:#fff;box-shadow:0 10px 30px rgba(5,150,105,.35)}
.outcome.esc{background:linear-gradient(110deg,#92400e,#d97706);color:#fff}
.outcome.watch{background:linear-gradient(110deg,#1e3a5f,#334e75);color:#fff}
.outcome .big{font-size:1.45rem;font-weight:800;letter-spacing:-.02em;line-height:1.1}
.outcome .sub{font-size:.82rem;opacity:.92;margin-top:3px;max-width:560px}
.outcome .seal{width:58px;height:58px;border-radius:50%;border:3px solid rgba(255,255,255,.85);display:flex;align-items:center;
  justify-content:center;font-size:1.7rem;font-weight:900;animation:stamp .6s .25s cubic-bezier(.2,1.6,.4,1) both}
@keyframes stamp{from{transform:scale(2.2) rotate(-18deg);opacity:0}to{transform:none;opacity:1}}
.outcome .nums{margin-left:auto;display:flex;gap:26px}
.outcome .num .v{font-family:var(--mono);font-size:1.6rem;font-weight:800;line-height:1}
.outcome .num .v.count{animation:count 2.2s cubic-bezier(.1,.8,.2,1) forwards;counter-reset:n var(--n)}
.outcome .num .v.count::after{content:counter(n)}
.outcome .num .v.rupee::before{content:'₹'}
@keyframes count{from{--n:0}to{--n:var(--to)}}
.outcome .num .l{font-size:.66rem;opacity:.85;text-transform:uppercase;letter-spacing:.06em;margin-top:4px}
.outcome .shine{position:absolute;top:0;left:-40%;width:30%;height:100%;
  background:linear-gradient(100deg,transparent,rgba(255,255,255,.28),transparent);animation:shine 2.8s 0.6s ease-in-out 2}
@keyframes shine{from{left:-40%}to{left:120%}}
</style>"""

_WAVE = ('<svg class="wave{cls}" viewBox="0 0 1200 60" preserveAspectRatio="none"><path fill="#fff" d="M0 30 Q 75 5 150 30 T 300 30 '
         'T 450 30 T 600 30 T 750 30 T 900 30 T 1050 30 T 1200 30 V60 H0 Z"/></svg>')


def hero(kpi: dict, cases_seen: int) -> str:
    saved = kpi.get("litres_saved_per_day", 0) / 1000
    return (CSS + '<div class="hero">' + _WAVE.format(cls="") + _WAVE.format(cls=" w2")
            + '<span class="drop"></span><span class="drop d2"></span><span class="drop d3"></span>'
            '<div class="row"><div><div class="logo">NEER<small>நீர்</small></div>'
            '<div class="live" style="margin-top:8px"><span class="dot"></span>LIVE · SIMULATED CITY (EPA NET3)</div></div>'
            '<div class="pitch">Investigates suspected leaks with evidence, acts only with human approval, and closes a '
            'case only when independent network measurements prove the repair worked.<br>'
            '<b>6 agents · 19 tools · 4 MCP servers · REST API · SQLite case database</b></div>'
            '<div class="stats">'
            f'<div class="stat"><div class="v">{cases_seen}</div><div class="l">cases this session</div></div>'
            f'<div class="stat"><div class="v">{kpi.get("repairs_verified", 0)}</div><div class="l">repairs proven</div></div>'
            f'<div class="stat"><div class="v">{saved:,.0f}</div><div class="l">m³/day saved</div></div>'
            '</div></div></div>')


STAGES = [("SUSPECT", "Sentinel"), ("QUESTION", "Skeptic"), ("INVESTIGATE", "Detective · Orchestrator"),
          ("ACT", "Field crew + human"), ("VERIFY", "Auditor"), ("REPLAN", "Orchestrator")]


def _stage(v: dict) -> int:
    """Which loop stage the case is in now (0-5), read from the case state."""
    ev, status = v.get("last_event", "start"), v.get("status", "open")
    if status in ("closed",) or v.get("verdict"):
        return 4 if status == "closed" else 5
    if ev in ("repaired",):
        return 4
    if ev in ("acoustic_no", "dig_empty", "not_fixed", "partly", "acoustic_inconclusive") and status == "open":
        return 5
    if v.get("plan_approved") or ev in ("acoustic_yes", "dig_rejected"):
        return 3
    if v.get("areas"):
        return 2
    if v.get("skeptic_verdict") or status in ("watch", "waiting"):
        return 1
    return 0


def mission(v: dict) -> str:
    if not v:
        return ""
    now = _stage(v)
    status = v.get("status", "open")
    finished = status in ("closed", "watch", "escalated", "no_alarm")
    out = ['<div class="mission">']
    for i, (name, who) in enumerate(STAGES):
        if status == "closed" and i == 5:
            cls = "done" if v.get("replans") else ""
        elif i < now or (finished and i == now):
            cls = "done"
        elif i == now:
            cls = "now"
        else:
            cls = ""
        if finished and i == now:
            cls += " good" if status == "closed" else (" bad" if status == "escalated" else "")
        mark = "✓" if "done" in cls else str(i + 1)
        loop = (f'<div class="loop">↺ ×{v.get("replans")}</div>' if i == 5 and v.get("replans") else "")
        out.append(f'<div class="mstep {cls}"><div class="bar"></div><div class="ball">{mark}</div>'
                   f'<div class="name">{name}</div><div class="who">{who}</div>{loop}</div>')
    out.append("</div>")
    return "".join(out)


def outcome(v: dict, kpi: dict) -> str:
    status = v.get("status")
    if status == "closed" and v.get("verdict") == "FIXED":
        m3 = int(round(kpi.get("litres_saved_per_day", 0) / 1000))
        inr = int(round(m3 * config.COST_PER_M3_INR))
        return ('<div class="outcome fixed"><div class="shine"></div><div class="seal">✓</div>'
                '<div><div class="big">Repair PROVEN · FIXED at 999:1</div>'
                f'<div class="sub">The Auditor measured the loss itself, before and after, hour by hour. '
                f'Contractor {v.get("contractor") or "released"}. {v.get("visits", 0)} field visits, '
                f'{v.get("replans", 0)} re-plans.</div></div>'
                '<div class="nums">'
                f'<div class="num"><div class="v count" style="--to:{m3}"></div><div class="l">m³ water saved / day</div></div>'
                f'<div class="num"><div class="v count rupee" style="--to:{inr}"></div>'
                f'<div class="l">per day at ₹{config.COST_PER_M3_INR}/m³ (assumed)</div></div>'
                '</div></div>')
    if status == "escalated":
        return ('<div class="outcome esc"><div class="seal">!</div><div><div class="big">Escalated to a human</div>'
                '<div class="sub">NEER stopped instead of guessing or working around a safety gate. '
                'The evidence and the full trace go with the case.</div></div></div>')
    if status in ("watch", "no_alarm"):
        return ('<div class="outcome watch"><div class="seal">◎</div><div><div class="big">No crew sent</div>'
                f'<div class="sub">{v.get("skeptic_reason") or "Nothing abnormal enough to act on."} '
                'Kept on WATCH and re-checked tomorrow.</div></div></div>')
    return ""


def toast_for(update: dict) -> tuple[str, str] | None:
    """(message, icon) for the moments worth a pop-up, else None."""
    for e in update.get("timeline") or []:
        t, agent = e.get("text", ""), e.get("agent", "")
        if agent == "Sentinel" and t.startswith("Alarm"):
            return "Sentinel raised an alarm", ":material/notifications_active:"
        if "LEAK NOISE HEARD" in t:
            return "Acoustic loggers heard the leak", ":material/hearing:"
        if "refused" in t.lower() and agent in ("Field Commander", "Orchestrator"):
            return "Safety validator refused the dig", ":material/gpp_bad:"
        if agent == "Auditor" and t.startswith("FIXED"):
            return "Repair proven FIXED", ":material/verified:"
        if agent == "Auditor" and t.startswith(("NOT FIXED", "PARTLY")):
            return "Auditor: repair did NOT hold - re-planning", ":material/replay:"
    return None


# ------------------------------------------------------------------ team chat view of the timeline
AVATAR = {"Sentinel": ("#0e7490", "SE"), "Skeptic": ("#dc2626", "SK"), "Detective": ("#2563eb", "DE"),
          "Orchestrator": ("#1e3a8a", "OR"), "Field Commander": ("#7c3aed", "FC"), "Auditor": ("#15803d", "AU"),
          "Supervisor": ("#b45309", "YOU")}
CHAT_CSS = """<style>
.chat{display:flex;flex-direction:column;gap:9px;max-height:620px;overflow-y:auto;padding:4px 4px 10px}
.msg{display:flex;gap:8px;align-items:flex-end;animation:pop .35s ease-out both}
@keyframes pop{from{transform:translateY(6px) scale(.98);opacity:0}to{transform:none;opacity:1}}
.msg .av{width:30px;height:30px;border-radius:50%;color:#fff;font-size:.62rem;font-weight:800;display:flex;
  align-items:center;justify-content:center;flex:none}
.msg .b{border-radius:14px 14px 14px 4px;padding:7px 11px;background:var(--surface2);border:1px solid var(--line);
  font-size:.8rem;line-height:1.35;max-width:88%}
.msg .who{font-size:.66rem;font-weight:800;letter-spacing:.03em;margin-bottom:2px}
.msg.human{flex-direction:row-reverse}
.msg.human .b{border-radius:14px 14px 4px 14px;background:#fef3c7;border-color:#fcd34d;color:#1f2937}
.msg.alert .b{border-color:#fca5a5;background:#fff1f2;color:#1f2937}
.msg.verdict .b{border-color:#86efac;background:#f0fdf4;color:#1f2937}
.msg .tag{display:inline-block;margin-left:6px;font-size:.6rem;font-weight:700;color:var(--muted);font-family:var(--mono)}
</style>"""


def chat_html(timeline: list[dict]) -> str:
    """The agents' timeline as a team chat: each agent has an avatar; humans speak on the right."""
    import html as _h
    rows = []
    for e in timeline:
        agent = e.get("agent", "")
        colour, ini = AVATAR.get(agent, ("#64748b", agent[:2].upper()))
        kind = e.get("kind", "info")
        cls = "human" if kind == "human" else ("alert" if kind == "alert" else ("verdict" if kind == "verdict" else ""))
        prov = e.get("provider")
        tag = f'<span class="tag">{_h.escape(str(prov).split(" ")[0])}</span>' if prov else ""
        rows.append(f'<div class="msg {cls}"><div class="av" style="background:{colour}">{ini}</div>'
                    f'<div class="b"><div class="who" style="color:{colour}">{_h.escape(agent)}{tag}</div>'
                    f'{_h.escape(e.get("text", ""))}</div></div>')
    return CHAT_CSS + '<div class="chat">' + "".join(rows) + "</div>"
