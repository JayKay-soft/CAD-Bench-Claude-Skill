#!/usr/bin/env python3
"""
verify.py -- the gate every cad-bench export passes through.

The model re-derives geometry from numbers you typed. If one number is wrong
the STL is a wrong part that looks right, and an STL carries no dimensions to
check it against afterwards. So nothing is written without passing here.

The reference volume is the kernel's own exact volume, which makes the check
"did tessellation lose anything it should not have" -- free, and tighter than
any hand computation. `wall_check` covers what volume and bounding box cannot
see: wall thicknesses, bore lands, clearances.

OUTPUT IS TERSE ON PURPOSE. A model gets run several times while it's being
built, and each run's stdout re-enters the calling agent's context. A dozen
lines of watertight/winding/bbox/radius detail on every routine success is
pure waste once the gate has proven itself once -- the interesting case is a
FAILURE, and that always prints in full because that's when the numbers
matter. Pass `verbose=True` to get the full report on a passing run too, e.g.
while first writing a model.
"""

from __future__ import annotations


class VerifyError(RuntimeError):
    """Raised when a part is not safe to write. Do not catch and continue."""


def _report(mesh, name, reference_volume, reference_label):
    """The full, multi-line report. Called on failure, or when verbose."""
    import numpy as np

    lo, hi = mesh.bounds
    r = np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1])
    vol = mesh.volume

    print(f"[{name}]")
    print(f"  watertight        : {mesh.is_watertight}")
    print(f"  winding_consistent: {mesh.is_winding_consistent}")
    print(f"  volume            : {vol:12.3f} mm^3")
    if reference_volume is not None:
        dv = abs(vol - reference_volume)
        rel = dv / reference_volume if reference_volume else float("inf")
        print(f"  {reference_label:<18}: {reference_volume:12.3f} mm^3   "
              f"delta {dv:.4f} ({rel * 100:.3f}%)")
    print(f"  bbox X            : {lo[0]:10.3f} .. {hi[0]:10.3f}")
    print(f"  bbox Y            : {lo[1]:10.3f} .. {hi[1]:10.3f}")
    print(f"  bbox Z            : {lo[2]:10.3f} .. {hi[2]:10.3f}")
    print(f"  radius (XY)       : {r.min():10.3f} .. {r.max():10.3f}")
    print(f"  triangles         : {len(mesh.faces)}")


def verify(mesh, name, reference_volume=None, tol=0.005, expect_bbox=None,
           reference_label="exact (kernel)", verbose=False):
    """
    Gate `mesh`. Raises VerifyError on anything meaning the part is wrong.

    On success, prints ONE line unless `verbose=True`. On failure, prints the
    full report first so the numbers that mattered are visible, then raises.
    """
    vol = mesh.volume
    problems = []
    if not mesh.is_watertight:
        problems.append("not watertight")
    if not mesh.is_winding_consistent:
        problems.append("winding inconsistent")
    if vol <= 0:
        problems.append(f"non-positive volume ({vol:.3f})")
    if reference_volume is not None and reference_volume > 0:
        rel = abs(vol - reference_volume) / reference_volume
        if rel > tol:
            problems.append(
                f"volume {vol:.3f} vs {reference_label} {reference_volume:.3f} "
                f"({rel * 100:.2f}% > {tol * 100:.2f}%)")
    if expect_bbox is not None:
        lo, hi = mesh.bounds
        elo, ehi = expect_bbox
        for got, want, ax in zip(lo, elo, "XYZ"):
            if want is not None and abs(got - want) > 0.05:
                problems.append(f"bbox {ax} min {got:.3f} != {want:.3f}")
        for got, want, ax in zip(hi, ehi, "XYZ"):
            if want is not None and abs(got - want) > 0.05:
                problems.append(f"bbox {ax} max {got:.3f} != {want:.3f}")

    if problems or verbose:
        _report(mesh, name, reference_volume, reference_label)

    if problems:
        raise VerifyError(f"{name}: " + "; ".join(problems))

    if verbose:
        print("  OK")
    else:
        lo, hi = mesh.bounds
        size = hi - lo
        note = ""
        if reference_volume is not None and reference_volume > 0:
            rel = abs(vol - reference_volume) / reference_volume
            note = f", {rel * 100:.3f}% vs {reference_label}"
        print(f"[{name}] OK  watertight  vol={vol:.1f} mm^3{note}  "
              f"bbox {size[0]:.1f}x{size[1]:.1f}x{size[2]:.1f}")
    return mesh


def wall_check(name, got, want, unit="mm", verbose=False):
    """
    Assert a dimension the bounding box cannot see -- a wall thickness, a bore
    land, a clearance to a rim. These are what make a part unprintable, and
    they are invisible in bbox and volume alike.

    Silent on pass unless `verbose=True` (checks accumulate quickly and a
    passing one carries no information); always prints and raises on fail.
    """
    ok = got >= want
    if not ok:
        print(f"  FAIL {name}: {got:.3f} {unit} (want >= {want:.3f})")
        raise VerifyError(f"{name}: {got:.3f} {unit} < required {want:.3f} {unit}")
    if verbose:
        print(f"  ok   {name}: {got:.3f} {unit} (want >= {want:.3f})")
    return got
