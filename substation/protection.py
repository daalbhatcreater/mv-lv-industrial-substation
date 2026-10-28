"""MV overcurrent protection: IDMT relays (IEC 60255-151), the LV incomer ACB
seen from the 11 kV side, and the transformer limits the settings have to
respect.

All currents in this module are 11 kV primary amps.
"""

import math
from dataclasses import dataclass

CURVES = {
    # IEC 60255-151: t = TMS * k / ((I/Is)^a - 1)
    "SI": (0.14, 0.02),
    "VI": (13.5, 1.0),
    "EI": (80.0, 2.0),
}
BREAKER_S = 0.06       # VCB interrupting time (3 cycles)
CTI_S = 0.30           # coordination time interval between numerical relays
RELAY_MIN_S = 0.03     # inherent operating time of the relay


@dataclass
class Relay:
    name: str
    ct_primary: float
    is_a: float                  # 51 pickup, primary amps
    tms: float
    curve: str = "SI"
    highset_a: float = None      # 50 element, primary amps
    highset_t: float = 0.05

    def t_relay(self, i):
        k, a = CURVES[self.curve]
        t = math.inf
        if i > 1.05 * self.is_a:
            t = self.tms * k / ((i / self.is_a) ** a - 1)
        if self.highset_a and i >= self.highset_a:
            t = min(t, self.highset_t)
        return max(t, RELAY_MIN_S)

    def t_clear(self, i):
        return self.t_relay(i) + BREAKER_S


@dataclass
class LVBreaker:
    """LV incomer ACB with long-time and definite short-time zones,
    instantaneous off. Current in LV amps."""
    name: str
    ir_a: float
    tr_s: float
    isd_a: float
    tsd_s: float
    ratio: float

    def t_clear_lv(self, i_lv):
        t = math.inf
        if i_lv > 1.2 * self.ir_a:
            t = self.tr_s * (6 * self.ir_a / i_lv) ** 2
        if i_lv >= 1.1 * self.isd_a:
            t = min(t, 1.2 * self.tsd_s + 0.02)
        return t

    def t_clear(self, i_hv):
        return self.t_clear_lv(i_hv * self.ratio)


def grade(relay: Relay, downstream, i_lo, i_hi, cti=CTI_S, points=400,
          tms_range=(0.05, 1.2)):
    """Smallest TMS (0.01 steps) for which the relay clears at least `cti`
    after the downstream device at every current in [i_lo, i_hi] where the
    downstream device operates. Returns None if no TMS in range works."""
    currents = [i_lo * (i_hi / i_lo) ** (k / (points - 1)) for k in range(points)]
    lo, hi = tms_range
    tms = lo
    while tms <= hi + 1e-9:
        relay.tms = round(tms, 2)
        ok = True
        for i in currents:
            t_down = downstream(i)
            if math.isinf(t_down):
                continue
            if relay.t_clear(i) < t_down + cti:
                ok = False
                break
        if ok:
            return relay.tms
        tms += 0.01
    return None


def transformer_damage(tr, i):
    """IEC 60076-5 thermal limit: 2 s at the transformer's own
    short-circuit current, I^2 t constant (HV amps)."""
    isc = tr.in_hv_a / tr.uk
    return 2.0 * (isc / i) ** 2 if i > 2 * tr.in_hv_a else math.inf


def inrush_point(tr, multiple=12.0, t=0.1):
    return multiple * tr.in_hv_a, t


@dataclass
class CT:
    primary: float
    secondary: float = 1.0
    alf: float = 20            # 5P20
    rated_va: float = 5.0
    rct_ohm: float = 1.5       # secondary winding resistance

    def effective_alf(self, burden_ohm):
        rb_rated = self.rated_va / self.secondary ** 2
        return self.alf * (self.rct_ohm + rb_rated) / (self.rct_ohm + burden_ohm)


def lead_burden(length_m, area_mm2=2.5, relay_va=0.1, secondary=1.0):
    r_lead = 2 * length_m * 0.0178 / area_mm2          # go and return, Cu
    return r_lead + relay_va / secondary ** 2
