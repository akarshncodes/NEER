"""NEER engine: the physics/statistics the agents call as tools."""
import numpy as np
from twin import *

class Brain:
    def __init__(self,sensors,history):
        self.S=list(sensors); self.si=[JI[s] for s in self.S]
        P=np.stack([h[0][:,self.si] for h in history]); Z=np.stack([h[1] for h in history])
        self.pn,self.ps=P.mean(0),np.maximum(P.std(0,ddof=1),0.05)
        self.zn,self.zs=Z.mean(0),np.maximum(Z.std(0,ddof=1),0.5)
        n=len(history)
        # leave-one-out spread of daily zone-excess estimates and pressure scores -> thresholds
        ex=[];sc=[]
        for k in range(n):
            rest=[history[i] for i in range(n) if i!=k]
            b=Brain.__new__(Brain); b.si=self.si
            Pr=np.stack([h[0][:,self.si] for h in rest]); Zr=np.stack([h[1] for h in rest])
            b.pn,b.ps=Pr.mean(0),np.maximum(Pr.std(0,ddof=1),0.05); b.zn,b.zs=Zr.mean(0),np.maximum(Zr.std(0,ddof=1),0.5)
            ex.append(b.zone_excess([history[k]])); sc.append(b.pscore([history[k]]))
        self.ex_se=np.maximum(np.std(ex,0,ddof=1),0.3)*1.2
        self.p_thr=np.max(sc)*1.25
        self.z_thr=4.0
    # --- Monitor tools ---
    def zone_excess(self,days,hours=slice(0,H)):
        z=np.mean([d[1] for d in days],0)
        w=1/self.zs[hours]**2
        ex=((z[hours]-self.zn[hours])*w).sum(0)/w.sum(0)            # L/s extra water entering each zone
        if Brain.common_mode:                                        # whole-city swings (weather, holidays) hit every zone
            n=np.maximum(np.abs((self.zn[hours]*w).sum(0)/w.sum(0)),1)
            f=np.median(ex/n); ex=ex-f*n
        return ex
    def presid(self,days,drop=()):
        r=self.pn-np.mean([d[0][:,self.si] for d in days],0)
        if drop: r=r.copy(); r[:,list(drop)]=0
        return r
    def pscore(self,days,drop=()): 
        z=self.presid(days,drop)/self.ps; return float(np.sqrt((z**2).mean()))
    def alarm(self,days):
        t=self.zone_excess(days)/(self.ex_se/np.sqrt(len(days)))
        return bool(t.max()>self.z_thr or self.pscore(days)>self.p_thr), t
    # --- Detective tool ---
    def locate(self,days,use_flow=True,weighted=True,size_fit=True,prior=None,res=None):
        n=len(days)
        r=self.presid(days) if res is None else res
        w=(1/self.ps) if weighted else np.full_like(self.ps,1/0.3)
        a=(r*w).ravel()
        ll=np.full(len(J),-np.inf)
        if use_flow:
            ex=self.zone_excess(days); t=ex/(self.ex_se/np.sqrt(n))
            lz=0.5*np.clip(t,0,None)**2
        for s in range(len(LIB_SIZES)):
            F=(FP[s][:,:,self.si]*w).reshape(len(J),-1)
            kfree=np.clip((F@a)/((F*F).sum(1)+1e-12),0,None)
            if use_flow and size_fit:
                q=np.clip(ex[JZ],0.5,None); k=q/QREF[s]
                k=np.sqrt(k*np.maximum(kfree,1e-6))                    # blend flow-size with pressure-fit
            else: k=kfree
            err=((a[None,:]-k[:,None]*F)**2).sum(1)
            ll=np.maximum(ll,-0.5*err/ (H*n**0 ) )
        ll=ll*self.temper
        if use_flow: ll=ll+lz[JZ]
        if prior is not None: ll=ll+np.log(prior+1e-12)
        p=np.exp(ll-ll.max()); return p/p.sum()
    temper=0.1
    common_mode=True

# --- Planner: turn a probability map into crew search areas ---
def plan_areas(post,searched_w,hops=1):
    p=post*searched_w; p=p/p.sum()
    best=None
    for j in J:
        a=area(j,hops); m=sum(p[JI[x]] for x in a)
        if best is None or m>best[0]: best=(m,j,a)
    return best
def search(post_fn,leaks,pd=0.9,soft=True,max_visits=6,rng=None,hops=1):
    """Visit areas in order of probability until every leak is found. Crew's listening device misses with prob 1-pd."""
    rng=rng or np.random.default_rng(0)
    remaining=set(leaks); w=np.ones(len(J)); found_at=[]
    post=post_fn(remaining)
    for v in range(1,max_visits+1):
        m,j,a=plan_areas(post,w,hops)
        hit=[l for l in remaining if l in a and rng.random()<pd]
        if hit:
            for l in hit: remaining.discard(l); found_at.append(v)
            if not remaining: break
            w=np.ones(len(J)); post=post_fn(remaining)          # Verifier: still leaking -> re-localise
        else:
            for x in a: w[JI[x]]*= (1-pd) if soft else 0.0
    return found_at, remaining
