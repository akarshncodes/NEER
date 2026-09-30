from engine import *
import json
rng=np.random.default_rng(99)
cases=[]
for k in range(50):
    c=City(500+k); hist=[c.day() for _ in range(3)]
    l=J[rng.integers(len(J))]; q=rng.uniform(15,40)
    d=c.day(leaks={l:area_for_flow(q)})
    cases.append((l,np.mean([h[0] for h in hist],0)-d[0]))
def acc(S):
    si=[JI[s] for s in S]; t=0
    for l,r in cases:
        a=r[:,si].ravel(); best=np.full(len(J),-np.inf)
        for s in range(len(LIB_SIZES)):
            F=FP[s][:,:,si].reshape(len(J),-1); k=np.clip((F@a)/((F*F).sum(1)+1e-12),0,None)
            best=np.maximum(best,-((a-k[:,None]*F)**2).sum(1))
        top=[J[i] for i in np.argsort(-best)[:3]]
        t+= 3*(top[0]==l)+ (l in area(top[0])) + (l in top)
    return t
S=[]
for _ in range(20):
    b=max((j for j in J if j not in S),key=lambda j:acc(S+[j])); S.append(b)
json.dump(S,open("smart20.json","w")); print(S)
