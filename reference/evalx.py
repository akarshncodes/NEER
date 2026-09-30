from engine import *
import json,pickle,sys
S20=json.load(open("smart20.json")); R20=list(np.random.default_rng(7).choice(J,20,replace=False))
def run(cases,cfg,temper=0.5,ndays=1,pd=1.0,soft=True,seed=0):
    Brain.temper=temper; rng=np.random.default_rng(seed); res={}
    for c in cases:
        b=Brain(cfg["sensors"],c["hist"]); days=c["ld"][:ndays]
        det,_=b.alarm(days)
        if cfg["name"]=="original":
            # vs twin, cosine, junction-by-junction, pressure only
            r=BASE[:,b.si]-np.mean([d[0][:,b.si] for d in days],0)
            a=r.ravel()-r.mean(); best=np.full(len(J),-np.inf)
            for s in range(len(LIB_SIZES)):
                F=FP[s][:,:,b.si].reshape(len(J),-1); F=F-F.mean(1,keepdims=True)
                best=np.maximum(best,(F@a)/(np.linalg.norm(F,axis=1)*np.linalg.norm(a)+1e-9))
            order=[J[i] for i in np.argsort(-best)]; fa=[i+1 for i,j in enumerate(order[:6]) if j==c["leak"]]
            fa=fa[:1]
        else:
            post=b.locate(days,use_flow=cfg["flow"],size_fit=cfg["flow"])
            fa,_=search(lambda rem:post,[c["leak"]],pd=pd,soft=soft,rng=rng,hops=cfg["hops"])
        v=fa[0] if fa else 99
        res.setdefault(c["q"],[]).append((det,v))
    out={}
    for q,l in res.items():
        n=len(l); out[q]=dict(detect=round(100*sum(d for d,_ in l)/n),v1=round(100*sum(v<=1 for _,v in l)/n),
                             v2=round(100*sum(v<=2 for _,v in l)/n),v3=round(100*sum(v<=3 for _,v in l)/n))
    allv=[v for l in res.values() for _,v in l]
    out["all"]=dict(v1=round(100*np.mean([v<=1 for v in allv])),v3=round(100*np.mean([v<=3 for v in allv])))
    return out
CFG={"original":dict(name="original",sensors=R20,flow=False,hops=0),
     "simple":dict(name="simple",sensors=S20,flow=False,hops=1),
     "neer":dict(name="neer",sensors=S20,flow=True,hops=1)}
