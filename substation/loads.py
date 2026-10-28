"""Plant load list and maximum demand.

Demand of each line = installed working kW x load factor / efficiency. The sum
is multiplied by a coincidence (diversity) factor for the whole plant.
"""

import math
from dataclasses import dataclass


@dataclass
class Load:
    name: str
    qty_working: int
    qty_standby: int
    kw: float            # rated output (motors) or input (others)
    pf: float
    efficiency: float
    load_factor: float
    starting: str = ""   # DOL, star-delta, soft starter, VFD

    @property
    def demand_kw(self):
        return self.qty_working * self.kw * self.load_factor / self.efficiency

    @property
    def demand_kvar(self):
        return self.demand_kw * math.tan(math.acos(self.pf))

    @property
    def installed_kw(self):
        return (self.qty_working + self.qty_standby) * self.kw


PLANT = [
    Load("Process pumps", 3, 1, 75, 0.86, 0.94, 0.80, "star-delta"),
    Load("Air compressors", 1, 1, 160, 0.88, 0.95, 0.85, "DOL"),
    Load("Cooling tower fans", 4, 0, 22, 0.84, 0.91, 0.80, "DOL"),
    Load("Belt conveyors", 6, 0, 30, 0.85, 0.92, 0.75, "DOL"),
    Load("ID / FD fans", 2, 0, 110, 0.95, 0.95, 0.80, "VFD"),
    Load("Process heaters", 1, 0, 300, 1.00, 1.00, 0.90),
    Load("HVAC and chillers", 1, 0, 180, 0.88, 1.00, 0.80),
    Load("Lighting", 1, 0, 60, 0.95, 1.00, 1.00),
    Load("Workshop and small power", 1, 0, 80, 0.85, 1.00, 0.50),
    Load("Admin and utilities", 1, 0, 40, 0.90, 1.00, 0.70),
]

DIVERSITY = 0.90
FUTURE_GROWTH = 0.20
PF_TARGET_WITH_APFC = 0.95


def max_demand(loads=PLANT, diversity=DIVERSITY):
    p = sum(l.demand_kw for l in loads) * diversity
    q = sum(l.demand_kvar for l in loads) * diversity
    s = math.hypot(p, q)
    return {"kw": p, "kvar": q, "kva": s, "pf": p / s,
            "installed_kw": sum(l.installed_kw for l in loads)}


def apfc_kvar(p_kw, pf_from, pf_to):
    return p_kw * (math.tan(math.acos(pf_from)) - math.tan(math.acos(pf_to)))
