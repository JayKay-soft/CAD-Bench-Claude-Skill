#!/usr/bin/env python3
"""
enclosure.py -- worked B-rep example for the cad-bench skill.

A rounded, hollow enclosure: filleted corners, shelled to a wall thickness,
chamfered rim and base, four bored bosses standing on the inside floor, and a
cable port through one wall.  Every one of those except the bosses is
impossible to do honestly in mesh CSG -- this is the part the `brep` backend
exists for.

Order matters and is the whole lesson: fillet the solid FIRST, then shell.
Shelling a sharp box and rounding afterwards gives a different (and usually
failing) result, because the fillet then has to negotiate a 2 mm wall
instead of a solid corner.

Run:
    <venv>/Scripts/python models/enclosure.py
Reads models/enclosure.params.json if present (written from the bench
handoff), builds, verifies against the kernel's exact volume, writes
models/enclosure.stl.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import brep as B

PARAMS = {
    "width":      80.0,   # X, outside
    "depth":      60.0,   # Y, outside
    "height":     30.0,   # Z, outside
    "wall":        2.4,   # shell thickness
    "corner_r":    6.0,   # vertical corner fillet
    "rim_cham":    0.8,   # chamfer on the outer top rim
    "base_cham":   0.6,   # chamfer on the outer bottom edge (elephant-foot relief)
    "boss_d":      7.0,   # internal boss outside diameter
    "bore_d":      2.9,   # boss bore (M3 self-tapping)
    "boss_inset": 11.0,   # boss centre inset from the outside walls
    "port_w":     16.0,   # cable port width
    "port_h":      9.0,   # cable port height
    "port_z":      8.0,   # port centre above the outside floor
}


def derive(P):
    d = dict(P)
    d["inner_w"] = P["width"] - 2 * P["wall"]
    d["inner_d"] = P["depth"] - 2 * P["wall"]
    d["inner_h"] = P["height"] - P["wall"]
    d["boss_wall"] = (P["boss_d"] - P["bore_d"]) / 2.0
    d["boss_h"] = P["height"] - P["wall"] - 2.0        # stop short of the rim
    d["bx"] = P["width"] / 2.0 - P["boss_inset"]
    d["by"] = P["depth"] / 2.0 - P["boss_inset"]
    # A corner fillet must leave the wall intact: the inner corner radius is
    # the outer one less the wall, and it has to stay positive.
    d["inner_r"] = P["corner_r"] - P["wall"]
    return d


def build(P):
    d = derive(P)

    # 1. Solid outer body, sitting on Z = 0, with rounded vertical corners.
    body = B.Box(P["width"], P["depth"], P["height"],
                 align=(B.Align.CENTER, B.Align.CENTER, B.Align.MIN))
    body = B.safe_fillet(body, B.vertical_edges(body), P["corner_r"],
                         what="corner fillet")

    # 2. Hollow it, leaving the top open.  Negative offset = inward.
    body = B.offset(body, amount=-P["wall"], openings=B.top_face(body))

    # 3. Chamfers.  The bottom outer loop is unambiguous once shelled (the
    #    floor is solid, so there is no inner edge at Z=0).  The top rim has
    #    both an outer and an inner loop, so take the outer one explicitly.
    if P["base_cham"] > 0:
        body = B.safe_chamfer(body, B.bottom_edges(body), P["base_cham"],
                              what="base chamfer")
    if P["rim_cham"] > 0:
        body = B.safe_chamfer(body, B.outer_of(B.top_edges(body)),
                              P["rim_cham"], what="rim chamfer")

    # 4. Bosses on the inside floor, then bore them.
    for sx in (-1, 1):
        for sy in (-1, 1):
            post = B.Cylinder(P["boss_d"] / 2.0, d["boss_h"],
                              align=(B.Align.CENTER, B.Align.CENTER, B.Align.MIN))
            body += B.Pos(sx * d["bx"], sy * d["by"], P["wall"]) * post
    for sx in (-1, 1):
        for sy in (-1, 1):
            hole = B.Cylinder(P["bore_d"] / 2.0, d["boss_h"] + 1.0,
                              align=(B.Align.CENTER, B.Align.CENTER, B.Align.MIN))
            body -= B.Pos(sx * d["bx"], sy * d["by"], P["wall"]) * hole

    # 5. Cable port through the -Y wall.
    port = B.Box(P["port_w"], P["wall"] * 4.0, P["port_h"])
    body -= B.Pos(0.0, -P["depth"] / 2.0, P["port_z"]) * port

    return body


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    P = dict(PARAMS)
    over = os.path.join(here, "enclosure.params.json")
    if os.path.exists(over):
        with open(over) as fh:
            P.update({k: float(v) for k, v in json.load(fh).items() if k in PARAMS})
        print(f"loaded overrides from {os.path.basename(over)}")

    d = derive(P)
    part = build(P)

    # Dimensions the bounding box cannot see, but the print depends on.
    B.wall_check("inner corner radius", d["inner_r"], 0.5)
    B.wall_check("boss wall", d["boss_wall"], 1.2)
    B.wall_check("port top to rim", P["height"] - P["wall"]
                 - (P["port_z"] + P["port_h"] / 2.0), 1.0)

    if B.solid_count(part) != 1:
        raise B.VerifyError(
            f"enclosure: {B.solid_count(part)} solids -- a boss is probably "
            "floating clear of the floor or a wall")

    B.export_verified(part, os.path.join(here, "enclosure.stl"), "enclosure",
                      tolerance=0.01, angular_tolerance=0.1,
                      expect_bbox=((-P["width"] / 2, -P["depth"] / 2, 0.0),
                                   ( P["width"] / 2,  P["depth"] / 2, P["height"])))


if __name__ == "__main__":
    main()
