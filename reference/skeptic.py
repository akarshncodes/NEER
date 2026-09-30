"""Skeptic agent tools: rule out look-alikes before anyone is sent to dig."""
from engine import *
VALVES=['107','113','115','145','147','153','163','171','186','202','223','245','269','289','305','307','311']
def twin_delta(event):
    p,f,bk=sim_day(**event); p0,f0,bk0=sim_day()
    return p-p0, (f@MZ.T-bk@BZ.T)-(f0@MZ.T-bk0@BZ.T)
def skeptic(b,day,ops_log=()):
    """Returns (verdict, reason, cleaned_day). verdict in {'no alarm','sensor fault','operation','temporary','LEAK'}"""
    p,z=day
    if not b.alarm([day])[0]: return "no alarm","",day
    # 1. sensor health: frozen or lone-wolf sensors
    bad=[]
    P=p[:,b.si]
    for k in range(len(b.si)):
        if P[6:,k].std()<0.01: bad.append(k)
    zp=np.abs((b.pn-P)/b.ps).mean(0)
    order=np.argsort(-zp)
    ex_t=(b.zone_excess([day])/b.ex_se).max()
    if zp[order[0]]>4 and zp[order[1]]<2.0 and ex_t<3: bad.append(int(order[0]))
    if bad:
        P2=P.copy(); P2[:,bad]=b.pn[:,bad]         # neutralise faulty sensor
        pp=p.copy(); pp[:,[b.si[k] for k in bad]]=P2[:,bad]; day2=(pp,z)
        if not b.alarm([day2])[0]: return "sensor fault",f"sensor(s) {[b.S[k] for k in bad]} faulty",day2
        day=day2; p=pp
    # 2. operations replay: re-run logged pump/valve actions in the twin and subtract their effect
    for ev in ops_log:
        dp,dz=twin_delta(ev); day2=(p-dp,z-dz)
        t=(b.zone_excess([day2])/b.ex_se).max()
        # a pump/valve action changes pressure but not how much water customers take; a leak changes both
        if not b.alarm([day2])[0] or t<b.z_thr: return "operation",f"explained by logged operation {ev}",day2
        day=day2; p,z=day2
    # 3. temporary: anomaly confined to a few hours and gone by the end of the day
    zh=np.sqrt((((b.pn-p[:,b.si])/b.ps)**2).mean(1))
    fh=((z-b.zn)/b.zs).max(1)
    hot=(zh>2.5)|(fh>4)
    late=(b.zone_excess([day],hours=slice(18,24))/(2*b.ex_se)).max()
    if (hot.sum()<=4 and not hot[-6:].any()) or (late<2.5 and not (zh[-6:]>2.5).any()):
        return "temporary","short event (fire-fighting / flushing), watching",day
    return "LEAK","persistent unexplained loss",day
