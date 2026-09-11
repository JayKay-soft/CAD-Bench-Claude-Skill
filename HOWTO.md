# How to use cad-bench

This is the end-user side of the workflow `SKILL.md` describes to Claude.
You don't run any of the commands below yourself — Claude does — this page
just shows what to expect at each step, using one of the skill's own worked
examples (`models/boss_plate.py`) so every number here is real output, not a
mockup.

## 1. Ask for a part

You don't need to name the skill or mention CAD tools. Any of these trigger it:

> "make me a mounting plate, four corner bosses for M4 heat-set inserts,
> bore each one, keep the wall around each insert at least 2 mm"

> "I need a bracket for a Pi Zero, rounded corners, wall thickness that
> survives a drop"

> "tweak the enclosure — thinner wall, still passes the checks"

## 2. Claude writes a parametric model, not a one-off shape

Every part is a small Python file against a real B-rep kernel
(`build123d`/OCCT — the same kernel lineage as FreeCAD), not a mesh
approximation. For the corner-boss plate above, that's `models/boss_plate.py`:
a rectangular plate, a cylindrical boss at each corner, each bored, corners
rounded. Running it directly (which Claude does, not you) prints one line on
success:

```
$ python models/boss_plate.py
[boss-plate] OK  watertight  vol=9400.1 mm^3, 0.010% vs exact (kernel)  bbox 60.0x40.0x12.0
  0.23 MB, 4572 tri -> boss_plate.stl
```

That line is a gate, not a progress message. It means: watertight, correctly
wound, the mesh is within 0.010% of the kernel's own exact volume (the gate
is 0.5%), and the bounding box is the size the parameters say it should be.
If any of that were false, **the file would not exist** — a failed check
deletes the STL rather than leaving a wrong part on disk.

## 3. Claude publishes a CAD Bench page — this is what you see

A live page with a slider for every dimension, a preview sketch, and a row
of pass/fail checks that update as you drag. For the corner-boss plate:

```
┌─ PLATE ──────────────────────────┐   TOP VIEW              BOSS, SECTION
│ Long side             [====|-] 60 mm │   ┌──────────────┐    ┌────┐
│ Short side            [===|--] 40 mm │   │ (o)      (o) │    │▓▓░░▓▓│
│ Thickness              [==|---]  3 mm │   │              │    │▓▓░░▓▓│
│ Hole inset from edges  [==|---]  8 mm │   │ (o)      (o) │    │▓▓░░▓▓│
├─ BOSS ────────────────────────────┤   └──────────────┘    └────┘
│ Diameter               [==|---] 10 mm │      60 × 40         Ø10×12 bore Ø4
│ Height                 [==|---] 12 mm │
│ Bore diameter          [=|----]  4 mm │
└────────────────────────────────────┘

  BOSS WALL   BOSS PROUD   RIM TO EDGE   HOLE PITCH X   HOLE PITCH Y   VOLUME
  3.00        9.0          3.00          44.0           24.0           9424 mm³

  ✓ Boss wall survives a heat-set insert      3.00 mm, want ≥ 2
  ✓ Boss stands proud of the plate            9.0 mm above the face
  ✓ Boss sits fully on the plate               3.00 mm rim to edge
  ✓ Bore clears the plate edge                 6.00 mm
  ✓ Opposite bosses do not overlap             centres 44 × 24 mm apart
  ✓ Bore is deeper than it is wide             12 mm deep, Ø4.0
```

(Real output from `boss_plate.py`'s own default values, read straight off a
running copy of the page — not invented for this doc.)

Each row is a physical constraint, not a generic linter — "does this wall
survive a heat-set insert being melted into it," not "is this number
positive." A `d.`/`p.` mixup or a typo in a check reads as a **red row**,
same as a real failure — that's why `scripts/check_bench.py` exists (see
below), and why a red row always means *something* is wrong, even if it
turns out to be the check's own arithmetic rather than the part.

## 4. You drag sliders, not edit numbers in a file

Type a value in the box next to a slider and it clamps to that slider's own
range and snaps to its step — 17.3 mm on a 0.5 mm-step slider lands on 17.5,
not 17.3, matching exactly what the slider itself would have landed on.
Move anything until every check is green, then press **"Hand these to
Claude"**.

## 5. Claude reads the values back and regenerates

The values you set are written to a small per-part store on the page; Claude
reads them, writes them to `models/boss_plate.params.json`, and re-runs the
model — same gate, same one-line-on-success report, now with your numbers
instead of the defaults. You get the new STL and a note on which check had
the least margin, since that's where the next change is most likely to break
something.

## What it won't do

Assemblies with mates, thread modelling, sheet-metal unfolding, FEA, or
output formats other than STL/STEP. If a request needs one of those, the
skill says so rather than quietly handing back something that looks right
and isn't.

## For anyone extending the skill itself

If you're editing `SKILL.md`, the models, or the bench template rather than
just using them: `references/verification.md` has the sliver-checking
method and the fudge-factor-tuning discipline this skill's own development
needed the hard way — worth reading before touching a boolean-heavy model.
