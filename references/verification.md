# Verification

Everything passes through `scripts/verify.py`. The reference is the kernel's
own exact volume, so the check is "did tessellation lose anything it should
not have" — free to write, and tighter than any hand computation.

## Why this is not optional

The model re-derives geometry from numbers you typed. If one number is wrong,
the STL is a wrong part that looks right — and an STL carries no dimensions,
no feature tree, nothing to check it against after the fact. `export_verified`
is the only gate between "the script ran" and "this is safe to print", and a
failure **deletes the file** rather than leaving a wrong part on disk.

`verify()` raises `VerifyError` on any of:

| gate | what a failure means |
|---|---|
| not watertight | a boolean produced an open shell, or two solids that should have merged are only touching |
| winding inconsistent | the solid is inside-out somewhere |
| volume ≤ 0 | inside-out overall, or a subtraction removed everything |
| mesh vs exact volume > 0.5% | tessellation is too coarse for the part's curvature |
| bbox off by > 0.05 mm | the part is not the size the parameters say |

On a raise: **stop**, print the numbers, fix the model. Never widen `tol` to
get past it — the tolerance is not the problem.

## Output is terse by design

A passing `export_verified` prints one line: `[name] OK  vol=... bbox=...` plus
a file-size line. A failing one prints the full per-axis report first, then
raises. This is deliberate — a model is run several times while it's being
built, and a dozen lines of routine detail on every pass is waste that
compounds across runs. Pass `verbose=True` for the full report on a pass too
(useful once, while first writing a model); don't work around the default by
adding your own duplicate prints.

## Tessellation: a pass is a pass

`export_verified(part, path, name, tolerance=0.01, angular_tolerance=0.1)`.

Measured on the shipped examples: 0.010% loss on `boss_plate`, 0.007% on
`enclosure`, 0.036% on `duct`. The gate is 0.5%, so all three clear it by
more than an order of magnitude.

**Do not re-export a passing part with a tighter tolerance because the margin
felt close.** 0.4% against a 0.5% gate is fine. Halving `tolerance` multiplies
triangle count and file size several-fold for geometry no printer resolves —
in one measured case a part went from 40k triangles / 2.0 MB to 127k / 6.3 MB
with no change a printer could reproduce. Tighten only when the gate actually
fails, which is the signal the tessellation genuinely is too coarse.

| `tolerance` | use |
|---|---|
| 0.05 | draft, fast preview |
| 0.01 | default; correct for FDM |
| 0.002 | resin, or small parts with tight curvature |

`angular_tolerance` (radians) controls facets around tight curves; 0.1 is
fine, drop to 0.05 only for small-radius fillets that must look smooth.

`export_verified` prints file size and triangle count, and says so when a part
exceeds 100k triangles.

## What volume cannot see

Volume and bounding box are blind to the dimensions that actually make a part
unprintable. A wall can go to 0.4 mm, a bore land to nothing, a boss can merge
into a sidewall — and the volume barely moves. Assert those directly:

```python
B.wall_check("inner corner radius", corner_r - wall, 0.5)
B.wall_check("boss wall", (boss_d - bore_d) / 2, 1.2)
B.wall_check("port top to rim", height - wall - port_top, 1.0)
```

`wall_check` prints the measured value and raises if it is under the
threshold. These mirror the bench's `checks()` rows — the page warns the user
while they tune, and the model refuses to export if they overrode it anyway.

Also assert piece count: `solid_count(part) != 1` on a part that should be one
piece means something is floating — a boss clear of the floor, a loft not
meeting its flange.

## Selection bugs do not raise

The most dangerous failure mode. If a fillet or chamfer targets the wrong edge
set, OCCT builds it happily: the part is watertight, the volume plausible, the
bounding box right — and the wrong edge is rounded.

Check by differential volume. Build with the feature at zero, build with it
on, and confirm the difference matches what that feature should remove:

```python
v0 = build(dict(P, rim_cham=0.0)).volume
v1 = build(P).volume
expected = outer_perimeter * P["rim_cham"] ** 2 / 2    # chamfer of side c
assert abs((v0 - v1) - expected) / expected < 0.05
```

A real example from this skill's own development: an earlier `outer_of()`
split rim loops by radial distance, which is invalid for a rounded rectangle —
the outer loop's radial range overlaps the inner one's. It returned 12 of 16
edges and the rim chamfer removed 168 mm³ where 86 mm³ was intended, thinning
a 2.4 mm wall from both sides. Nothing raised. The differential check caught
it in one run.

## Slivers: watertight and volume-correct is not enough

`export_verified`'s gates (watertight, winding, volume, bbox) can all pass
while the mesh still carries real degenerate triangles — a boolean can
produce a technically valid, correct-volume solid that hides slivers down to
1e-6 mm² at 1000:1+ edge-aspect-ratio underneath those gates. This happened
twice on the same real part before it was checked directly instead of
inferred.

Check it directly, the same way every time:

```python
import trimesh, numpy as np
m = trimesh.load(path)
areas = m.area_faces
groups = trimesh.grouping.group_rows(m.edges_sorted)
counts = np.array([len(g) for g in groups])
print("min_area:", areas.min(), "under_0.02:", int((areas < 0.02).sum()),
      "non_manifold_edges:", int((counts != 2).sum()), "bodies:", m.body_count)
```

Every edge should be shared by **exactly 2 faces** (a real 2-manifold, no
cracks); `bodies` should be 1; nothing should sit near-zero area relative to
the part's own typical face size.

**A suspicious-looking tessellation is a hypothesis, not a finding — check
both, trust the number when they disagree.** A fan of triangles converging on
one point, a webbed pattern, an oddly dense cluster: these are real signals
worth investigating, but they are not proof by themselves. One revision of
this skill's own development read a fan-of-triangles as a degenerate sliver
and added an unneeded 0.75 mm shave to avoid it; measuring the actual face
areas later showed that exact configuration had *zero* degenerate faces —
the visual pattern was just how the kernel tessellates a shared edge, not a
sign of a defect. Reading shape takes longer and is more ambiguous than
reading a number; when they conflict, the number wins.

**When a fix needs a real boolean between two independently-built shapes,
verify with the SAME rigor before AND after — never re-use a verification
result from a different geometry configuration.** A collapse/cleanup pass,
an epsilon, a trim radius that was measured clean on one variant of a part
is not evidence it stays clean on a different bearing angle, position, or
sibling variant of the same part — re-run the same measurement on every
configuration the model actually ships, not just the one open in front of you.

## Tuning a fudge-factor parameter (shave / overlap / epsilon)

Some fixes need a small deliberate offset — a shave to avoid a flush
coincidence, a trim-radius overlap to avoid a knife-edge boolean, a tiny
epsilon so two features don't share an exact boundary. Two rules, learned
the slow way:

1. **The safe range is often not monotonic — sweep it, don't guess a
   cautious-feeling round number.** Both "too small" and "too big" can fail
   while a value in between works; a bigger, safer-*feeling* value is not
   automatically a safer *actual* one. Sweep a real range (`for v in
   [0.05, 0.1, 0.15, 0.2, 0.3, 0.5, ...]`), measure sliver count (see above)
   at each, on **every** variant/configuration the model ships — and use the
   smallest value that is *actually verified* clean everywhere, not the
   first one that happened to work once. A part in this skill's own history
   shipped with a shave 7x larger than the real measured minimum, cutting
   far more material than the geometry required, because the first
   safe-looking value was never re-challenged.
2. **Give the swept value a distinctive, greppable name where it's
   declared, with the sweep result in the comment right there** —
   `PAD_SHAVE = 0.10  # swept 0.0-0.30 mm, only this passed both variants`,
   not a bare literal buried inside a function body. The next person (you,
   later) re-tuning this needs to find the constant and its prior sweep in
   one grep, not re-derive from scratch which line the magic number lives on.
3. **A value swept and verified on one kernel is not evidence for another.**
   An exact BREP kernel (build123d/OCCT) and a mesh-CSG kernel (trimesh/
   manifold3d) fail at completely different points for the "same" fix — a
   flush (zero-gap) join was perfectly clean on the exact kernel but needed
   a real, separately-swept minimum on the mesh kernel for the same
   geometric idea. Re-sweep per kernel; don't port a number across them.

## Add a feature by integrating it, not assembling it

The instinct when adding a hole, boss, or bore to an existing solid is to
build the new feature as an independent primitive and boolean it against
the host afterward (extrude a plain box, then subtract a cylinder for its
hole). That boolean is exactly where slivers come from: two independently
tessellated meshes being forced to agree along whatever curve their
intersection produces.

Prefer building the feature directly into the host's own construction
instead, when the feature's geometry allows it:

```python
# WRONG-shaped instinct -- two independent tessellations reconciled after
# the fact by a 3D boolean, prone to earcut/mesh-boolean slivers regardless
# of position (verified: this failed at ~9 of 12 arbitrary positions tested).
box = _aabb(...)
hole = _z_cyl(radius, z0, z1)
box_with_hole = _diff(box, hole)

# RIGHT-shaped instinct -- the hole is part of the SAME 2D profile before
# there is anything to reconcile. One tessellation, not two.
profile = Polygon([...]).difference(Point(cx, cy).buffer(radius, resolution=16))
part = extrude_polygon(profile, height)
```

This isn't always available — a bore drilled at a compound angle through a
curved, already-raked face can't always collapse to one profile — but reach
for it first. Fall back to a real boolean (with the sweep discipline above,
and the sliver check applied to its actual output) only once the feature
genuinely can't be expressed as part of the host's own profile.

## The bench page has its own checker

Recipe bugs are the same shape — they render rather than throw. Run
`python scripts/check_bench.py <bench.html>` before publishing; it evaluates
every recipe at defaults and at every slider extreme and exits non-zero on any
problem. See `references/bench-artifact.md`.

## After it passes

Report to the user:

- volume and bounding box
- which `wall_check` / bench check had the **least margin** — that is where
  the next parameter change will break something
- file size and triangle count if either is unusual
