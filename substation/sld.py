"""Single-line diagram of the substation, written as draw.io and PNG from
the design results."""

from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch

W, H = 1100, 820

STYLE = {
    "src": ("#e8e8e8", "#555555", "rounded=1;"),
    "tx": ("#ffffff", "#1f3864", "shape=ellipse;"),
    "brk": ("#ffffff", "#000000", ""),
    "bus": ("#000000", "#000000", ""),
    "board": ("#d5e8d4", "#82b366", "rounded=1;"),
    "relay": ("#fff2cc", "#7f6000", ""),
    "cable": ("#f5f5f5", "#666666", ""),
    "note": ("none", "none", "text;strokeColor=none;fillColor=none;"),
}


@dataclass
class Node:
    id: str
    label: str
    x: float
    y: float
    w: float
    h: float
    kind: str

    @property
    def cx(self):
        return self.x + self.w / 2


def build(d):
    tr, lv, mv, cab = d["transformer"]["tr"], d["lv"], d["mv"], d["cable"]
    p = d["protection"]
    nodes = [
        Node("U1", "11 kV utility feeder 1", 45, 20, 170, 34, "src"),
        Node("U2", "11 kV utility feeder 2", W - 250, 20, 170, 34, "src"),
        Node("IN1", f"IN1 VCB {mv['ir_a']} A<br>{mv['isc_ka']:g} kA 3 s", 80, 80, 100, 40, "brk"),
        Node("IN2", f"IN2 VCB {mv['ir_a']} A<br>{mv['isc_ka']:g} kA 3 s", W - 215, 80, 100, 40, "brk"),
        Node("R-IN", f"50/51, 50N/51N<br>CT {p['inc'].ct_primary:g}/1, SI TMS {p['inc'].tms:.2f}",
             195, 82, 160, 36, "relay"),
        Node("MVBUS", f"11 kV section 1: {mv['busbar_a']} A, {mv['isc_ka']:g} kA 3 s, "
             f"IEC 62271-200", 60, 160, W / 2 - 120, 8, "bus"),
        Node("MVBUS2", "11 kV section 2", W / 2 + 60, 160, W / 2 - 120, 8, "bus"),
        Node("BC", "BC VCB", W / 2 - 45, 144, 90, 40, "brk"),
        Node("TF1", f"TF1 VCB {mv['ir_a']} A", 390, 200, 100, 36, "brk"),
        Node("TF2", f"TF2 VCB {mv['ir_a']} A", W - 490, 200, 100, 36, "brk"),
        Node("R-TF", f"50/51 CT {p['tf'].ct_primary:g}/1 5P20<br>SI TMS {p['tf'].tms:.2f}, "
             f"50 at {p['tf'].highset_a / 1e3:.2f} kA", 195, 200, 180, 36, "relay"),
        Node("C1", f"3C x {cab.size_mm2} mm2 Al XLPE<br>11 kV, {cab.length_m:g} m", 375, 270, 130, 40, "cable"),
        Node("C2", f"3C x {cab.size_mm2} mm2 Al XLPE<br>11 kV, {cab.length_m:g} m", W - 505, 270, 130, 40, "cable"),
        Node("TR1", f"TR1 {tr.kva} kVA<br>11/0.433 kV Dyn11<br>uk {100 * tr.uk:g} %", 370, 345, 140, 70, "tx"),
        Node("TR2", f"TR2 {tr.kva} kVA<br>11/0.433 kV Dyn11<br>uk {100 * tr.uk:g} %", W - 510, 345, 140, 70, "tx"),
        Node("TRP", "Buchholz, WTI, OTI, PRV<br>trip TF1 / TF2", 200, 362, 160, 36, "note"),
        Node("LI1", f"LV-I1 ACB {lv['frame_a']} A<br>Ir {lv['ir_a']:.0f} A, Ii off", 390, 450, 100, 40, "brk"),
        Node("LI2", f"LV-I2 ACB {lv['frame_a']} A<br>Ir {lv['ir_a']:.0f} A, Ii off", W - 490, 450, 100, 40, "brk"),
        Node("LVBUS", f"415 V PCC section 1: {lv['busbar_a']} A, {lv['icw_ka']} kA 1 s, Form 4b",
             60, 530, W / 2 - 120, 8, "bus"),
        Node("LVBUS2", "415 V PCC section 2", W / 2 + 60, 530, W / 2 - 120, 8, "bus"),
        Node("LBC", f"LV-BC ACB<br>{lv['frame_a']} A", W / 2 - 45, 514, 90, 40, "brk"),
        Node("MCC1", "MCC-1<br>pumps, conveyors", 80, 640, 120, 46, "board"),
        Node("MCC2", "MCC-2<br>compressors, fans", 220, 640, 120, 46, "board"),
        Node("PDB", "Process heaters", 360, 640, 120, 46, "board"),
        Node("APFC", f"APFC panel<br>{d['transformer']['apfc_kvar']:.0f}+ kvar", 620, 640, 120, 46, "board"),
        Node("HVAC", "HVAC / chillers", 760, 640, 120, 46, "board"),
        Node("LDB", "Lighting, small<br>power, admin", 900, 640, 120, 46, "board"),
        Node("NOTE", "IN1 / IN2 / BC and LV-I1 / LV-I2 / LV-BC each interlocked "
             "so that only two of three are closed: the transformers are never paralleled "
             f"({d['faults']['lv_parallel']['ik_ka']:.0f} kA would exceed the {lv['icw_ka']} kA board)",
             60, 740, 980, 30, "note"),
    ]
    edges = [("U1", "IN1"), ("U2", "IN2"), ("IN1", "MVBUS"), ("IN2", "MVBUS2"),
             ("MVBUS", "TF1"), ("MVBUS2", "TF2"), ("TF1", "C1"), ("TF2", "C2"),
             ("C1", "TR1"), ("C2", "TR2"), ("TR1", "LI1"), ("TR2", "LI2"),
             ("LI1", "LVBUS"), ("LI2", "LVBUS2")]
    edges += [("LVBUS", n) for n in ("MCC1", "MCC2", "PDB")]
    edges += [("LVBUS2", n) for n in ("APFC", "HVAC", "LDB")]
    edges = [(a, b, {}) for a, b in edges]
    # bus couplers join the two sections side by side
    edges += [("MVBUS", "BC", {"side": True}), ("BC", "MVBUS2", {"side": True}),
              ("LVBUS", "LBC", {"side": True}), ("LBC", "LVBUS2", {"side": True})]
    return {n.id: n for n in nodes}, edges


def _route(a: Node, b: Node, opts=None):
    """Orthogonal polyline from a to b in drawing coordinates (y down)."""
    opts = opts or {}
    if opts.get("side"):
        y = a.y + a.h / 2 if a.kind == "bus" else b.y + b.h / 2
        return [(a.x + a.w, y), (b.x, y)]
    bx = b.x + opts["entry"] * b.w if "entry" in opts else b.cx
    if "level" in opts or "entry" in opts:
        ym = opts.get("level", (a.y + a.h + b.y) / 2)
        return [(a.cx, a.y + a.h), (a.cx, ym), (bx, ym), (bx, b.y)]
    if a.kind == "ups" and b.kind == "batt":
        y = a.y + a.h / 2
        return [(a.x + a.w, y), (b.x, y)]
    if a.kind == "bus":
        x0 = min(max(b.cx, a.x + 4), a.x + a.w - 4)
        return [(x0, a.y + a.h), (x0, b.y)] if abs(x0 - b.cx) < 1 else \
            [(x0, a.y + a.h), (x0, b.y - 10), (b.cx, b.y - 10), (b.cx, b.y)]
    if b.kind == "bus":
        return [(a.cx, a.y + a.h), (a.cx, b.y)]
    if abs(a.cx - b.cx) < 1:
        return [(a.cx, a.y + a.h), (b.cx, b.y)]
    ym = b.y - 14 if b.kind in ("rack", "ats") else (a.y + a.h + b.y) / 2
    return [(a.cx, a.y + a.h), (a.cx, ym), (b.cx, ym), (b.cx, b.y)]


def render_png(nodes, edges, path, title):
    fig = plt.figure(figsize=(W / 80, H / 80))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    for a, b, opts in edges:
        pts = _route(nodes[a], nodes[b], opts)
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color="#333333", lw=0.9, zorder=1)
    for n in nodes.values():
        fill, edge, _ = STYLE[n.kind]
        text = n.label.replace("<br>", "\n")
        if n.kind == "bus":
            ax.add_patch(Rectangle((n.x, n.y), n.w, n.h, color="black", zorder=2))
            right = n.id in ("MVBUS", "LVBUS2")
            ax.text(n.x + n.w if right else n.x, n.y - 4, text, fontsize=7.5, weight="bold",
                    va="bottom", ha="right" if right else "left", zorder=3)
            continue
        if n.kind == "note":
            ax.text(n.x, n.y + n.h / 2, text, fontsize=6.5, va="center", style="italic",
                    color="#444444")
            continue
        box = FancyBboxPatch((n.x, n.y), n.w, n.h,
                             boxstyle="round,pad=0,rounding_size=6" if "rounded" in STYLE[n.kind][2]
                             or n.kind in ("tx", "gen") else "square,pad=0",
                             facecolor=fill, edgecolor=edge, lw=1.0, zorder=2)
        ax.add_patch(box)
        ax.text(n.cx, n.y + n.h / 2, text, fontsize=6.3 if n.kind != "brk" else 5.8,
                ha="center", va="center", zorder=3)
    ax.text(W / 2, H - 12, title, ha="center", fontsize=9, weight="bold")
    fig.savefig(path, dpi=110)
    plt.close(fig)


def write_drawio(nodes, edges, path, title):
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    for n in nodes.values():
        fill, edge, extra = STYLE[n.kind]
        if n.kind == "bus":
            style = ("fillColor=#000000;strokeColor=#000000;labelPosition=center;"
                     f"verticalLabelPosition=top;align={'right' if n.id in ('MVBUS', 'LVBUS2') else 'left'};"
                     "verticalAlign=bottom;fontStyle=1;fontSize=11;html=1;")
        elif n.kind == "note":
            style = extra + "align=left;fontStyle=2;fontSize=9;html=1;"
        else:
            style = f"{extra}whiteSpace=wrap;html=1;fillColor={fill};strokeColor={edge};fontSize=9;"
        cells.append(
            f'<mxCell id={quoteattr(n.id)} value={quoteattr(n.label)} style={quoteattr(style)} '
            f'vertex="1" parent="1"><mxGeometry x="{n.x:g}" y="{n.y:g}" width="{n.w:g}" '
            f'height="{n.h:g}" as="geometry"/></mxCell>')
    for k, (a, b, opts) in enumerate(edges):
        na, nb = nodes[a], nodes[b]
        style = "edgeStyle=orthogonalEdgeStyle;rounded=0;endArrow=none;html=1;"
        points = ""
        if opts.get("side"):
            style += "exitX=1;exitY=0.5;entryX=0;entryY=0.5;"
        elif opts:
            pts = _route(na, nb, opts)[1:-1]
            points = '<Array as="points">' + "".join(
                f'<mxPoint x="{x:g}" y="{y:g}"/>' for x, y in pts) + "</Array>"
            style += f"exitX=0.5;exitY=1;entryX={opts.get('entry', 0.5):g};entryY=0;"
        elif na.kind == "bus":
            ex = (min(max(nb.cx, na.x + 4), na.x + na.w - 4) - na.x) / na.w
            style += f"exitX={ex:.4f};exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;"
        elif nb.kind == "bus":
            ex = (na.cx - nb.x) / nb.w
            style += f"exitX=0.5;exitY=1;entryX={ex:.4f};entryY=0;entryDx=0;entryDy=0;"
        elif na.kind == "ups" and nb.kind == "batt":
            style += "exitX=1;exitY=0.5;entryX=0;entryY=0.5;"
        else:
            style += "exitX=0.5;exitY=1;entryX=0.5;entryY=0;"
        cells.append(f'<mxCell id="e{k}" style={quoteattr(style)} edge="1" parent="1" '
                     f'source={quoteattr(a)} target={quoteattr(b)}>'
                     f'<mxGeometry relative="1" as="geometry">{points}</mxGeometry></mxCell>')
    xml = (f'<mxfile host="drawio"><diagram name={quoteattr(escape(title))}>'
           f'<mxGraphModel dx="{W}" dy="{H}" grid="1" gridSize="10" page="1" '
           f'pageWidth="{W}" pageHeight="{H}"><root>' + "".join(cells) +
           '</root></mxGraphModel></diagram></mxfile>\n')
    with open(path, "w") as fh:
        fh.write(xml)
