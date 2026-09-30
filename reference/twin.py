"""NEER reliability lab: simulated city (Net3) with realistic noise, leaks and look-alike events."""
import os, numpy as np, wntr, networkx as nx, warnings
from wntr.network.controls import ControlAction, Control
from wntr.network import LinkStatus
warnings.filterwarnings("ignore")
NET=os.path.join(os.path.dirname(wntr.__file__),"library","networks","Net3.inp")
H=24
wn0=wntr.network.WaterNetworkModel(NET)
J=list(wn0.junction_name_list); JI={j:i for i,j in enumerate(J)}
G=nx.Graph(wn0.to_graph().to_undirected())
DEM_PATS=sorted({d.pattern_name for j in J for d in wn0.get_node(j).demand_timeseries_list if d.pattern_name})
def C_of(A): return 0.75*A*np.sqrt(2*9.81)          # orifice leak -> EPANET emitter coefficient
def leak_lps(A,p=40): return 1000*C_of(A)*np.sqrt(p)

def sim_day(dmult=None, hourly=None, leaks=None, pump_trip=None, closed_pipe=None, fire=None):
    """One day of hourly pressures (H x nJ). dmult: per-junction demand factor; hourly: per-hour demand factor;
    leaks: {node: area}; pump_trip: (start_h, end_h) pump 10 off; closed_pipe: pipe name; fire: (node, lps, h0, h1)."""
    wn=wntr.network.WaterNetworkModel(NET)
    wn.options.time.duration=(H-1)*3600
    if dmult is not None:
        for j,s in dmult.items():
            for d in wn.get_node(j).demand_timeseries_list: d.base_value*=s
    if hourly is not None:
        for p in DEM_PATS:
            pat=wn.get_pattern(p); pat.multipliers=np.array(pat.multipliers)*hourly
    for n,A in (leaks or {}).items(): wn.get_node(n).emitter_coefficient=C_of(A)
    if pump_trip:
        pump=wn.get_link("10")
        for t,st,nm in ((pump_trip[0],LinkStatus.Closed,"trip_off"),(pump_trip[1],LinkStatus.Open,"trip_on")):
            wn.add_control(nm,Control._time_control(wn,t*3600,"SIM_TIME",False,ControlAction(pump,"status",st)))
    if closed_pipe:
        wn.get_link(closed_pipe).initial_status=LinkStatus.Closed
    if fire:
        n,lps,h0,h1=fire; pat=np.zeros(24); pat[h0:h1]=1
        wn.add_pattern("fire",pat); wn.get_node(n).add_demand(lps/1000,"fire")
    r=wntr.sim.EpanetSimulator(wn).run_sim()
    return r.node["pressure"][J].values, r.link["flowrate"][METERS].values*1000, r.node["demand"][BULK].values*1000

# ---- zones (District Metered Areas) and flow meters on their boundaries ----
import networkx.algorithms.community as _C
_comms=_C.greedy_modularity_communities(G,cutoff=5,best_n=5)
ZONE={n:i for i,c in enumerate(_comms) for n in c}
for n in wn0.tank_name_list+wn0.reservoir_name_list: ZONE[n]=-1
NZ=5
METERS=[l for l in wn0.link_name_list if ZONE[wn0.get_link(l).start_node_name]!=ZONE[wn0.get_link(l).end_node_name]]
# signed incidence: zone inflow = M @ flows
MZ=np.zeros((NZ,len(METERS)))
for k,l in enumerate(METERS):
    a,b=ZONE[wn0.get_link(l).start_node_name],ZONE[wn0.get_link(l).end_node_name]
    if b>=0: MZ[b,k]+=1
    if a>=0: MZ[a,k]-=1
JZ=np.array([ZONE[j] for j in J])
BULK=["203","35","123","15"]          # bulk customers (industry / bulk connections) with their own smart meters
BZ=np.zeros((NZ,len(BULK)))
for k,b in enumerate(BULK): BZ[ZONE[b],k]=1
BASE,_,_=sim_day()
class City:
    """A 'real' city = twin + hidden demand bias + daily/hourly variation + sensor noise."""
    def __init__(self,seed,bias=0.10,daily=0.03,hourly=0.03,sn=0.1):
        self.r=np.random.default_rng(seed); self.bias={j:self.r.normal(1,bias) for j in J}
        self.daily,self.hourly,self.sn=daily,hourly,sn
        self.mbias=self.r.normal(1,0.02,len(METERS))          # each flow meter reads 2% off (constant)
    def day(self,**ev):
        d={j:self.bias[j]*self.r.normal(1,self.daily) for j in J}
        h=self.r.normal(1,self.hourly,24)
        p,f,bk=sim_day(d,h,**ev)
        bk=bk*self.r.normal(1,0.01,bk.shape)                      # bulk-meter readings (1% noise)
        p=p+self.r.normal(0,self.sn,p.shape)
        f=f*self.mbias*self.r.normal(1,0.01,f.shape)             # +1% random meter noise
        return p,(f@MZ.T)-(bk@BZ.T)       # pressures, zone inflow minus metered bulk use (H x NZ), L/s

# fingerprint library: pressure drop pattern a leak at each junction causes (twin, no noise)
LIB_SIZES=(0.0004,0.0012,0.003)
FP=np.stack([np.stack([BASE-sim_day(leaks={j:A})[0] for j in J]) for A in LIB_SIZES])  # S x nJ x H x nJ

def area(j,hops=1): return (set(nx.single_source_shortest_path_length(G,j,cutoff=hops))&set(J))

# leak flow each library fingerprint corresponds to (L/s), per size & junction
QREF=np.array([[1000*C_of(A)*np.sqrt(max(BASE[:,JI[j]].mean(),1)) for j in J] for A in LIB_SIZES])
def area_for_flow(q,p=40): return q/1000/(0.75*np.sqrt(2*9.81)*np.sqrt(p))
