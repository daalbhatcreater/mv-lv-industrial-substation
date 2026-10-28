"""Equipment data and fault levels for the 11 kV / 415 V substation.

    Utility 11 kV feeder 1 --VCB IN1--+--VCB BC--+--VCB IN2-- Utility 11 kV feeder 2
                                      |          |
                                VCB TF1        VCB TF2
                                  | MV cable     | MV cable
                                 TR1            TR2        11/0.433 kV Dyn11
                                  |              |
                         ACB LV-I1 +--ACB LV-BC--+ ACB LV-I2    415 V PCC
                                   (2 of 3 closed)

Each transformer is sized to carry the whole plant, so either incomer or
either transformer can be lost. On both boards only two of the three breakers
(two incomers and the bus coupler) may be closed, which stops the transformers
being paralleled.

Fault currents use the IEC 60909-0 equivalent source method:
cmax = 1.10 at 11 kV, 1.05 at 415 V; cmin = 1.00 at 11 kV, 0.95 at 415 V.
"""

import math
from dataclasses import dataclass

MV_KV = 11.0
LV_V = 415.0


@dataclass
class Grid:
    sk_max_mva: float = 350.0
    sk_min_mva: float = 250.0
    r_over_x: float = 0.1


# IS 2026 / IEC 60076 standard ratings with typical impedance and losses
TRANSFORMERS = {
    # kVA: (uk %, no-load loss kW, load loss kW)
    1000: (5.00, 1.40, 10.5),
    1250: (5.00, 1.65, 12.5),
    1600: (6.25, 2.00, 15.5),
    2000: (6.25, 2.40, 19.0),
    2500: (6.25, 2.90, 23.0),
}


@dataclass
class Transformer:
    kva: int
    ur_hv_kv: float = 11.0
    ur_lv_kv: float = 0.433

    @property
    def uk(self):
        return TRANSFORMERS[self.kva][0] / 100

    @property
    def p0_kw(self):
        return TRANSFORMERS[self.kva][1]

    @property
    def pk_kw(self):
        return TRANSFORMERS[self.kva][2]

    @property
    def in_hv_a(self):
        return self.kva * 1e3 / (math.sqrt(3) * self.ur_hv_kv * 1e3)

    @property
    def in_lv_a(self):
        return self.kva * 1e3 / (math.sqrt(3) * LV_V)

    @property
    def ratio(self):
        return self.ur_hv_kv / self.ur_lv_kv

    def impedance_lv(self, apply_kt=True):
        """Ohms referred to the LV side, with KT (IEC 60909-0, 6.3.3)."""
        ur, sr = self.ur_lv_kv * 1e3, self.kva * 1e3
        z = self.uk * ur ** 2 / sr
        r = self.pk_kw * 1e3 * ur ** 2 / sr ** 2
        x = math.sqrt(z * z - r * r)
        kt = 0.95 * 1.05 / (1 + 0.6 * x / (ur ** 2 / sr)) if apply_kt else 1.0
        return complex(r, x) * kt

    def efficiency(self, load_kva, pf):
        frac = load_kva / self.kva
        p_out = load_kva * pf
        losses = self.p0_kw + self.pk_kw * frac ** 2
        return p_out / (p_out + losses)

    def regulation(self, frac, pf):
        """Approximate full-load regulation, ur cos + ux sin (+ second-order term)."""
        ur = self.pk_kw / self.kva
        ux = math.sqrt(self.uk ** 2 - ur ** 2)
        sin = math.sqrt(1 - pf * pf)
        e = frac * (ur * pf + ux * sin)
        return e + (frac * (ux * pf - ur * sin)) ** 2 / 2


@dataclass
class MVCable:
    size_mm2: int
    length_m: float
    r_ohm_km: float     # AC at 90 degC
    x_ohm_km: float
    k: float = 94.0     # aluminium, XLPE, 90 -> 250 degC


# 3-core Al XLPE 11 kV (UE) cables, typical maker data
MV_CABLES = {
    70: (0.568, 0.115, 165), 95: (0.411, 0.109, 200), 120: (0.325, 0.105, 225),
    150: (0.265, 0.102, 255), 185: (0.211, 0.099, 290), 240: (0.161, 0.096, 335),
}


def kappa(r_over_x):
    return 1.02 + 0.98 * math.exp(-3 * r_over_x)


def mv_fault(grid: Grid, c=1.1, sk=None):
    sk = sk or grid.sk_max_mva
    z = c * (MV_KV * 1e3) ** 2 / (sk * 1e6)
    x = z / math.sqrt(1 + grid.r_over_x ** 2)
    zq = complex(grid.r_over_x * x, x)
    ik = c * MV_KV * 1e3 / (math.sqrt(3) * abs(zq))
    return {"ik_ka": ik / 1e3, "ip_ka": kappa(grid.r_over_x) * math.sqrt(2) * ik / 1e3,
            "z": zq, "x_over_r": 1 / grid.r_over_x}


def lv_fault(grid: Grid, tr: Transformer, n_parallel=1, case="max"):
    """Three-phase fault at the LV PCC with n transformers in parallel."""
    c_mv, c_lv = (1.1, 1.05) if case == "max" else (1.0, 0.95)
    sk = grid.sk_max_mva if case == "max" else grid.sk_min_mva
    zq = c_mv * (MV_KV * 1e3) ** 2 / (sk * 1e6) / tr.ratio ** 2
    xq = zq / math.sqrt(1 + grid.r_over_x ** 2)
    z = complex(grid.r_over_x * xq, xq) + tr.impedance_lv(apply_kt=(case == "max")) / n_parallel
    ik = c_lv * LV_V / (math.sqrt(3) * abs(z))
    return {"ik_ka": ik / 1e3, "ip_ka": kappa(z.real / z.imag) * math.sqrt(2) * ik / 1e3,
            "ik_hv_a": ik / tr.ratio, "z": z}
