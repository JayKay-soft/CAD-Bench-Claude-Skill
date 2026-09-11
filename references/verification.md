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
