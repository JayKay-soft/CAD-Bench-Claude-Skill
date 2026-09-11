#!/usr/bin/env python3
"""
boss_plate.py -- the simplest worked example.

A rectangular plate with a cylindrical boss at each corner, each bored for a
screw or a heat-set insert, and a rounded outline.

It is here to show that the B-rep kernel is a fine tool for plain prismatic
work too -- there is no second "simple parts" backend to choose, and no
hand-computed reference volume to get wrong. Add `corner_r` and it rounds;
nothing about the model has to change shape to accommodate that.

Run:
    <venv>/Scripts/python models/boss_plate.py
Reads models/boss_plate.params.json if present, verifies, writes
models/boss_plate.stl.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import brep as B

PARAMS = {
    "plate_x":  60.0,   # long side
    "plate_y":  40.0,   # short side
    "plate_t":   3.0,   # plate thickness
    "inset":     8.0,   # boss/hole centre inset from each edge
    "boss_d":   10.0,   # boss outside diameter
    "boss_h":   12.0,   # boss height from the plate underside
    "bore_d":    4.0,   # bore diameter
    "corner_r":  3.0,   # plate corner fillet (0 for square corners)
}


def derive(P):
    d = dict(P)
    d["hx"] = P["plate_x"] / 2.0 - P["inset"]
    d["hy"] = P["plate_y"] / 2.0 - P["inset"]
    d["boss_wall"] = (P["boss_d"] - P["bore_d"]) / 2.0
    d["proud"] = P["boss_h"] - P["plate_t"]
    d["edge"] = P["inset"] - P["boss_d"] / 2.0
    return d


def build(P):
    d = derive(P)
    plate = B.Box(P["plate_x"], P["plate_y"], P["plate_t"],
                  align=(B.Align.CENTER, B.Align.CENTER, B.Align.MIN))
    if P["corner_r"] > 0:
        plate = B.safe_fillet(plate, B.vertical_edges(plate), P["corner_r"],
                              what="plate corner")

    for sx in (-1, 1):
        for sy in (-1, 1):
            boss = B.Cylinder(P["boss_d"] / 2.0, P["boss_h"],
                              align=(B.Align.CENTER, B.Align.CENTER, B.Align.MIN))
            plate += B.Pos(sx * d["hx"], sy * d["hy"], 0.0) * boss
    for sx in (-1, 1):
        for sy in (-1, 1):
            bore = B.Cylinder(P["bore_d"] / 2.0, P["boss_h"] + 2.0,
                              align=(B.Align.CENTER, B.Align.CENTER, B.Align.MIN))
            plate -= B.Pos(sx * d["hx"], sy * d["hy"], -1.0) * bore

    return plate


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    P = dict(PARAMS)
    over = os.path.join(here, "boss_plate.params.json")
    if os.path.exists(over):
        with open(over) as fh:
            P.update({k: float(v) for k, v in json.load(fh).items() if k in PARAMS})
        print(f"loaded overrides from {os.path.basename(over)}")

    d = derive(P)
    part = build(P)

    B.wall_check("boss wall", d["boss_wall"], 1.2)
    B.wall_check("boss proud of plate", d["proud"], 1.0)
    B.wall_check("boss rim to plate edge", d["edge"], 0.5)

    if B.solid_count(part) != 1:
        raise B.VerifyError(f"boss_plate: {B.solid_count(part)} solids, expected 1")

    B.export_verified(part, os.path.join(here, "boss_plate.stl"), "boss-plate",
                      expect_bbox=((-P["plate_x"] / 2, -P["plate_y"] / 2, 0.0),
                                   ( P["plate_x"] / 2,  P["plate_y"] / 2,
                                     P["boss_h"])))


if __name__ == "__main__":
    main()
