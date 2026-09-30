"""The pipe network (EPA Net3), its zones (DMAs), meters and search areas.

Everything here is fixed geometry: it does not change between days or cities.
"""
from __future__ import annotations

import os
from functools import lru_cache

import networkx as nx
import networkx.algorithms.community as nxc
import numpy as np
import wntr

from neer import config

NET3_PATH = os.path.join(os.path.dirname(wntr.__file__), "library", "networks", "Net3.inp")


def load_model() -> wntr.network.WaterNetworkModel:
    """A fresh copy of the Net3 model, set to 1-hour steps over one day."""
    wn = wntr.network.WaterNetworkModel(NET3_PATH)
    wn.options.time.duration = (config.HOURS - 1) * 3600
    wn.options.time.hydraulic_timestep = 3600
    wn.options.time.report_timestep = 3600
    return wn


class Network:
    """Fixed facts about the city network, computed once."""

    def __init__(self) -> None:
        wn = load_model()
        self.wn = wn
        self.junctions: list[str] = list(wn.junction_name_list)
        self.jindex = {j: i for i, j in enumerate(self.junctions)}
        self.graph = nx.Graph(wn.to_graph().to_undirected())
        self.coords = {n: wn.get_node(n).coordinates for n in wn.node_name_list}

        # ---- zones (District Metered Areas) by modularity clustering, stable names
        comms = nxc.greedy_modularity_communities(self.graph, cutoff=config.N_ZONES, best_n=config.N_ZONES)
        comms = sorted(comms, key=lambda c: min(c))
        self.zone_names = [f"Z{i + 1}" for i in range(len(comms))]
        self.node_zone: dict[str, int] = {n: i for i, c in enumerate(comms) for n in c}
        for n in list(wn.tank_name_list) + list(wn.reservoir_name_list):
            self.node_zone[n] = -1                      # storage & sources sit outside zones
        self.junction_zone = np.array([self.node_zone[j] for j in self.junctions])

        # ---- flow meters = links crossing a zone border; signed incidence (zone inflow = MZ @ flows)
        self.meters: list[str] = [
            l for l in wn.link_name_list
            if self.node_zone[wn.get_link(l).start_node_name] != self.node_zone[wn.get_link(l).end_node_name]
        ]
        self.MZ = np.zeros((len(self.zone_names), len(self.meters)))
        for k, l in enumerate(self.meters):
            a = self.node_zone[wn.get_link(l).start_node_name]
            b = self.node_zone[wn.get_link(l).end_node_name]
            if b >= 0:
                self.MZ[b, k] += 1
            if a >= 0:
                self.MZ[a, k] -= 1

        # ---- bulk customers (own smart meters)
        self.bulk = list(config.BULK_CUSTOMERS)
        self.BZ = np.zeros((len(self.zone_names), len(self.bulk)))
        for k, b in enumerate(self.bulk):
            self.BZ[self.node_zone[b], k] = 1

        self.sensors = list(config.PRESSURE_SENSORS)
        self.sensor_index = [self.jindex[s] for s in self.sensors]

    # ------------------------------------------------------------ helpers
    def zone_of(self, junction: str) -> str:
        return self.zone_names[self.node_zone[junction]]

    def zone_junctions(self, zone: str) -> list[str]:
        z = self.zone_names.index(zone)
        return [j for j in self.junctions if self.node_zone[j] == z]

    def area(self, junction: str) -> list[str]:
        """Search area = the junction plus neighbouring junctions (1 hop)."""
        near = nx.single_source_shortest_path_length(self.graph, junction, cutoff=1)
        return sorted(n for n in near if n in self.jindex)

    def area_pipe_km(self, junction: str) -> float:
        a = set(self.area(junction))
        total = 0.0
        for p in self.wn.pipe_name_list:
            link = self.wn.get_link(p)
            if link.start_node_name in a and link.end_node_name in a:
                total += link.length
        return round(total / 1000, 2)


@lru_cache(maxsize=1)
def get_network() -> Network:
    """The shared, cached Network object."""
    return Network()


def area_for_flow(lps: float, pressure_m: float = config.REF_PRESSURE_M) -> float:
    """Orifice area (m^2) that leaks `lps` litres/second at `pressure_m`."""
    return lps / 1000 / (config.DISCHARGE_COEF * np.sqrt(2 * config.GRAVITY) * np.sqrt(pressure_m))


def emitter_coef(area_m2: float) -> float:
    """EPANET emitter coefficient for an orifice of this area."""
    return config.DISCHARGE_COEF * area_m2 * np.sqrt(2 * config.GRAVITY)
