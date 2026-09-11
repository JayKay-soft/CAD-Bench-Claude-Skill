#!/usr/bin/env python3
"""
duct.py -- worked LOFT example for the cad-bench skill.

A rectangle-to-round transition duct with a bolted base flange: the shape a
fan outlet or a vacuum adapter needs, and one with no CSG equivalent at all
-- there is no combination of boxes and cylinders that produces a surface
which is a rectangle at one end and a circle at the other.

Two lessons here:

1. LOFT NEEDS THE BUILDER CONTEXT. `loft()` consumes the sketches pending on
   a BuildPart, in the order they were added -- unlike fillet/chamfer/offset,
   it has no algebra-mode form that takes a list of profiles.

2. DO NOT SHELL A LOFT. `offset(amount=-t)` on a lofted transition asks OCCT
   to offset a doubly-curved surface, which is slow and often fails outright.
   Loft the OUTER profiles, loft the INNER profiles, and subtract. That gives
   exact control of the wall at both ends and always builds.

Run:
    <venv>/Scripts/python models/duct.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import brep as B

PARAMS = {
    "rect_w":     70.0,   # inlet, X
    "rect_d":     45.0,   # inlet, Y
    "round_d":    50.0,   # outlet diameter
    "height":     65.0,   # inlet face to outlet face
    "wall":        2.5,   # duct wall
    "flange_t":    4.0,   # base flange thickness
    "flange_m":   10.0,   # flange margin beyond the inlet rect
    "bolt_d":      4.5,   # flange bolt clearance
    "bolt_inset":  5.5,   # bolt centre inset from the flange edge
    "inlet_fil":   6.0,   # fillet on the inlet rectangle corners
}


def derive(P):
    d = dict(P)
    d["flange_w"] = P["rect_w"] + 2 * P["flange_m"]
    d["flange_d"] = P["rect_d"] + 2 * P["flange_m"]
    d["bx"] = d["flange_w"] / 2.0 - P["bolt_inset"]
    d["by"] = d["flange_d"] / 2.0 - P["bolt_inset"]
    d["throat_in"] = P["round_d"] - 2 * P["wall"]
    # Area ratio tells you whether the transition is a diffuser or a nozzle;
    # a big step either way separates the flow.
    d["area_in"] = P["rect_w"] * P["rect_d"]
    d["area_out"] = 3.14159265 * (P["round_d"] / 2.0) ** 2
    d["area_ratio"] = d["area_out"] / d["area_in"]
    return d


def _loft_between(w, dpt, dia, z0, z1, fil):
    """One lofted shell: rounded rectangle at z0 -> circle at z1."""
    with B.BuildPart() as bp:
        with B.BuildSketch(B.Plane.XY.offset(z0)):
            B.RectangleRounded(w, dpt, fil)
        with B.BuildSketch(B.Plane.XY.offset(z1)):
            B.Circle(dia / 2.0)
        B.loft()
    return bp.part


def build(P):
    d = derive(P)
    z0 = P["flange_t"]
    z1 = P["flange_t"] + P["height"]

    outer = _loft_between(P["rect_w"], P["rect_d"], P["round_d"],
                          z0, z1, P["inlet_fil"])
    inner = _loft_between(P["rect_w"] - 2 * P["wall"],
                          P["rect_d"] - 2 * P["wall"],
                          d["throat_in"],
                          z0 - 1.0, z1 + 1.0,
                          max(P["inlet_fil"] - P["wall"], 0.1))

    flange = B.Box(d["flange_w"], d["flange_d"], P["flange_t"],
                   align=(B.Align.CENTER, B.Align.CENTER, B.Align.MIN))
    flange = B.safe_fillet(flange, B.vertical_edges(flange),
                           P["bolt_inset"] * 1.2, what="flange corner")

    body = flange + outer - inner

    for sx in (-1, 1):
        for sy in (-1, 1):
            bolt = B.Cylinder(P["bolt_d"] / 2.0, P["flange_t"] + 2.0,
                              align=(B.Align.CENTER, B.Align.CENTER, B.Align.MIN))
            body -= B.Pos(sx * d["bx"], sy * d["by"], -1.0) * bolt

    return body


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    P = dict(PARAMS)
    over = os.path.join(here, "duct.params.json")
    if os.path.exists(over):
        with open(over) as fh:
            P.update({k: float(v) for k, v in json.load(fh).items() if k in PARAMS})
        print(f"loaded overrides from {os.path.basename(over)}")

    d = derive(P)
    part = build(P)

    B.wall_check("duct wall", P["wall"], 1.2)
    B.wall_check("bolt land", P["bolt_inset"] - P["bolt_d"] / 2.0, 1.5)
    B.wall_check("outlet bore", d["throat_in"], 5.0)
    print(f"  note area ratio out/in = {d['area_ratio']:.3f}")

    if B.solid_count(part) != 1:
        raise B.VerifyError(
            f"duct: {B.solid_count(part)} solids -- the loft probably does not "
            "meet the flange; check that z0 equals flange_t")

    B.export_verified(part, os.path.join(here, "duct.stl"), "duct",
                      tolerance=0.01, angular_tolerance=0.1,
                      expect_bbox=((-d["flange_w"] / 2, -d["flange_d"] / 2, 0.0),
                                   ( d["flange_w"] / 2,  d["flange_d"] / 2,
                                     P["flange_t"] + P["height"])))


if __name__ == "__main__":
    main()
