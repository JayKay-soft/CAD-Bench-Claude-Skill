#!/usr/bin/env python3
"""
inspect_stl.py -- structured first look at an existing STL, before writing a
single line of a reconstruction model.

Born from a real miss: a first pass at reverse-engineering a part sampled a
handful of GUESSED Z heights (0, 1, 2, 5, 10, 17.5, 25...) and silently
skipped the two heights (0.2 and 15) where a blind hole actually lived,
reading its mouth-chamfer rim as a "valley" in an unrelated outer profile
instead. The fix is not "sample more carefully" -- it's not sampling at all:
every distinct Z the mesh actually has vertices at is cheap to list exactly,
so list it and never guess. See references/stl-reverse-engineering.md for
the full method this script exists to make fast.

    python scripts/inspect_stl.py part.stl
    python scripts/inspect_stl.py part.stl --z 0.2           # detail one Z
    python scripts/inspect_stl.py part.stl --z 0.2 --center 0 0

Output:
  - volume, bbox, watertight (the same facts export_verified gates on --
    this script's volume number is what you compare a reconstruction's
    kernel-exact volume against, NOT the reconstruction's own tessellation)
  - every distinct Z with a vertex count, so nothing at a real feature
    boundary goes unsampled
  - with --z: every unique (x,y) at that height, radius from --center
    (default the mesh's own XY centroid), sorted by angle, WITH A GAP
    REPORT -- radius values are clustered and printed as separate bands,
    because two unrelated loops (an outer profile, an inner bore's rim)
    can share one Z and look like one confusing ring if you don't
    separate them before trying to read the shape off the numbers.
"""

import argparse
import sys

import numpy as np


def _load(path):
    import trimesh
    m = trimesh.load(path)
    if isinstance(m, trimesh.Scene):
        m = trimesh.util.concatenate(m.dump())
    return m


def _radius_bands(radii, gap=0.05):
    """Cluster sorted radius values into bands separated by >= gap mm --
    the cheap signal that two concentric loops, not one, share this Z."""
    order = np.argsort(radii)
    bands = [[radii[order[0]]]]
    for r in radii[order[1:]]:
        if r - bands[-1][-1] > gap:
            bands.append([r])
        else:
            bands[-1].append(r)
    return [(min(b), max(b), len(b)) for b in bands]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stl", help="path to the STL to inspect")
    ap.add_argument("--z", type=float, default=None,
                    help="detail every vertex at this Z (mm), within --tol")
    ap.add_argument("--tol", type=float, default=0.01,
                    help="Z / point matching tolerance, mm (default 0.01)")
    ap.add_argument("--center", type=float, nargs=2, default=None, metavar=("X", "Y"),
                    help="centre for radius measurement (default: mesh XY centroid)")
    args = ap.parse_args()

    m = _load(args.stl)
    v = m.vertices

    print(f"[{args.stl}]")
    print(f"  volume       : {m.volume:.4f} mm^3   <- compare a reconstruction's")
    print(f"                                          KERNEL-EXACT volume against")
    print(f"                                          THIS, not its own tessellation")
    print(f"  watertight   : {m.is_watertight}")
    print(f"  bbox         : {m.bounds[0]} .. {m.bounds[1]}")

    if args.z is None:
        zs = np.unique(np.round(v[:, 2] / args.tol) * args.tol)
        print(f"  distinct Z   : {len(zs)} values (tol {args.tol} mm)")
        for z in zs:
            n = int(np.sum(np.abs(v[:, 2] - z) < args.tol))
            print(f"    z={z:10.4f}   {n:5d} vertices")
        print()
        print("  Re-run with --z <value> on any height that looks like it might")
        print("  carry more than one feature (unexpected vertex count, a height")
        print("  that isn't a multiple of an obvious pattern, etc).")
        return

    mask = np.abs(v[:, 2] - args.z) < args.tol
    pts = v[mask][:, :2]
    if len(pts) == 0:
        sys.exit(f"no vertices within {args.tol} mm of z={args.z}")
    uniq = np.unique(np.round(pts, 5), axis=0)
    cx, cy = args.center if args.center else uniq.mean(axis=0)
    radii = np.sqrt((uniq[:, 0] - cx) ** 2 + (uniq[:, 1] - cy) ** 2)

    print(f"\n  z={args.z}: {len(uniq)} unique points, centre ({cx:.4f}, {cy:.4f})")
    bands = _radius_bands(radii)
    print(f"  {len(bands)} radius band(s) -- each is very likely a SEPARATE loop/feature:")
    for lo, hi, n in bands:
        spread = "" if hi - lo < 1e-4 else f" (spread {hi - lo:.4f})"
        shape = "circle" if hi - lo < 1e-3 else "faceted/irregular"
        print(f"    r = {lo:.4f} .. {hi:.4f}{spread}   {n:4d} points   -> looks like a {shape} loop")
    if len(bands) > 1:
        print("\n  MULTIPLE BANDS AT ONE Z: do not read this as one shape. Separate")
        print("  the points by which band they fall in (filter on radius) before")
        print("  trying to interpret either loop's profile.")


if __name__ == "__main__":
    main()
