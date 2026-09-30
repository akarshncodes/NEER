from evalx import *
import json
R={}
# ---------- A. Fast verification: sequential test, hour by hour ----------
def sprt(b,z,hours,q,infl):
    A=np.log(99)
    llr=0
    for t,(zh,h) in enumerate(hours):
        e=zh[z]-b.zn[h,z]; s=b.zs[h,z]*infl
        llr+=(e*q-q*q/2)/s**2
        if llr>A: return "NOT FIXED",t+1
        if llr<-A: return "FIXED",t+1
    return "UNDECIDED",len(hours)
out={}
for infl in (1.5,2.0):
  for q in (5,10,20,40):
    res=[]
    for k in range(25):
        c=City(20000+q*100+k); hist=[c.day() for _ in range(7)]; b=Brain(S20,hist)
        l=J[np.random.default_rng(k+q).integers(len(J))]; z=JZ[JI[l]]
        pre=[c.day(leaks={l:area_for_flow(q)})]; qest=max(b.zone_excess(pre)[z],1.0)
        for truth,L in (("FIXED",{}),("NOT FIXED",{l:area_for_flow(q)})):
            days=[c.day(leaks=L) for _ in range(3)]
            hrs=[(d[1][h],h) for d in days for h in range(24)]
            v,t=sprt(b,z,hrs,qest,infl); res.append((truth,v,t))
    acc=np.mean([v==tr for tr,v,_ in res]); und=np.mean([v=="UNDECIDED" for _,v,_ in res])
    med=float(np.median([t for _,v,t in res if v!="UNDECIDED"])) if any(v!="UNDECIDED" for _,v,_ in res) else None
    out[f"{infl}_{q}"]=dict(correct=round(100*acc),undecided=round(100*und),median_hours=med)
    print("infl",infl,"q",q,out[f"{infl}_{q}"],flush=True)
R["sprt"]=out
# ---------- B. Listen before dig ----------
cases=pickle.load(open("cases.pkl","rb")); Brain.temper=0.1
rng=np.random.default_rng(3)
SENS,FPR=0.85,0.05
orig_digs=[];neer=[]
for c in cases:
    # original plan: dig at top-ranked junction each time until found (max 6)
    b=Brain(R20,c["hist"]); days=c["ld"][:3]
    r=BASE[:,b.si]-np.mean([d[0][:,b.si] for d in days],0); a=r.ravel()-r.mean(); best=np.full(len(J),-np.inf)
    for s in range(len(LIB_SIZES)):
        F=FP[s][:,:,b.si].reshape(len(J),-1); F=F-F.mean(1,keepdims=True)
        best=np.maximum(best,(F@a)/(np.linalg.norm(F,axis=1)*np.linalg.norm(a)+1e-9))
    order=[J[i] for i in np.argsort(-best)]
    n=next((i+1 for i,j in enumerate(order[:6]) if j==c["leak"]),None)
    orig_digs.append((n is not None, (n-1) if n else 6))
    # NEER: acoustic survey of area; dig only on positive
    b=Brain(S20,c["hist"]); post=b.locate(days); w=np.ones(len(J)); wasted=0; found=False
    for v in range(1,7):
        m,j,ar=plan_areas(post,w)
        inside=c["leak"] in ar
        pos=(rng.random()<SENS) if inside else (rng.random()<FPR)
        if pos:
            if inside: found=True; break
            wasted+=1
        for x in ar: w[JI[x]]*= (1-SENS) if not pos else 0.5
    neer.append((found,wasted,v))
R["dig"]=dict(orig_found6=round(100*np.mean([f for f,_ in orig_digs])),orig_wasted_per_case=round(float(np.mean([w for _,w in orig_digs])),2),
              neer_found6=round(100*np.mean([f for f,_,_ in neer])),neer_found3=round(100*np.mean([f and v<=3 for f,_,v in neer])),
              neer_wasted_per_case=round(float(np.mean([w for _,w,_ in neer])),2),neer_surveys_median=float(np.median([v for f,_,v in neer if f])))
print(R["dig"])
json.dump(R,open("results_v3.json","w"),indent=1)
