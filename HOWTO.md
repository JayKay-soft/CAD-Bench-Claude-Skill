# How to use cad-bench

This is the end-user side of the workflow `SKILL.md` describes to Claude.
You don't run any of the commands below yourself — Claude does — this page
just shows what to expect at each step. Every screenshot below is a real
capture of the skill's own worked example (`models/boss_plate.py`) running
in a browser, not a mockup.

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

A live page with a slider for every dimension, a preview sketch that
redraws as you move them:

![Sliders on the left, a live top-view and section sketch on the right](docs/screenshots/01-sliders-drawing.png)

Type a value directly in the box next to a slider instead of dragging, and
it clamps to that slider's own range and snaps to its step — 17.3 mm on a
0.5 mm-step slider lands on 17.5, not 17.3, matching exactly what the slider
itself would have landed on.

## 4. A row of checks, not a generic linter

Below the sketch, the numbers that actually matter for this part — and a
pass/fail row for every physical constraint, in plain language:

![Six constraint rows, all green: boss wall thickness, standoff height, edge clearance, bore depth](docs/screenshots/02-checks-green.png)

Each row is a real constraint, not "is this number positive" — *"does this
wall survive a heat-set insert being melted into it,"* not a generic range
check. Push a value past what the part can actually take and a row turns
red, with the exact number that failed:

![One red row -- boss wall thinned to 0.50mm against a 2mm minimum -- five still green](docs/screenshots/04-checks-red.png)

(This one is real too: the boss diameter was set to 5 mm against a 4 mm
bore, so the wall left around the insert is only 0.5 mm — the check catches
it and says by how much, not just pass/fail.)

## 5. Hand the values back to Claude

Once every check is green, the bottom of the page has the constants your
sliders landed on, ready to hand off:

![A textarea to paste constants back in, and a generated const block for the model's parameters](docs/screenshots/03-handoff.png)

Inside the Claude Code app this panel also shows a **"Hand these to
Claude"** button (it needs a small capability the app grants; a plain
browser falls back to **Copy parameters**, shown above). Either way, Claude
reads the values back, writes them to `models/boss_plate.params.json`, and
re-runs the model — same gate, same one-line-on-success report, now with
your numbers instead of the defaults. You get the new STL and a note on
which check had the least margin, since that's where the next change is
most likely to break something.

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
