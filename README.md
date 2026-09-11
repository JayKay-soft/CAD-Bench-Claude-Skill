# cad-bench

A [Claude Code](https://claude.com/claude-code) skill that turns a plain-English
part description into a verified, printable STL — modelled in Python against a
real CAD kernel, with an interactive slider page for tuning dimensions before
export.

```
you: "make me an enclosure for a Pi Zero 2 W, rounded corners, USB-C cutout"
        │
        ▼
Claude writes a parametric model (fillet → shell → chamfer → bosses → port)
        │
        ▼
publishes a CAD Bench page — sliders, live constraint checks, a preview sketch
        │
        ▼
you drag the sliders until the checks go green, click "Hand these to Claude"
        │
        ▼
Claude reads the values back and exports a gated, watertight STL
```

## Why

Most "AI CAD" demos stop at *"here's a box with a hole in it."* This skill is
built for the part after that one — the enclosure with rounded corners and a
shelled cavity, the round-to-rectangular duct, the bracket where a wall
thickness of 1.8 mm instead of 2.2 mm is the difference between a part that
prints and one that doesn't.

It does that by modelling against **[build123d](https://build123d.readthedocs.io/)**,
a real B-rep kernel (OCCT — the same lineage as FreeCAD and OpenCascade), not
a mesh approximation. Fillets are fillets. Shells are shells. Every export is
gated by a script that checks the mesh is watertight, correctly wound, and
within 0.5% of the kernel's own exact volume — and it **deletes the file**
rather than hand you a part that's wrong.

## Requirements

- Python 3.10+
- A venv with `build123d` installed (pulls the OCCT kernel — the one real
  cost, ~500 MB download):

  ```
  python -m venv cad-bench-venv
  cad-bench-venv/Scripts/python -m pip install build123d trimesh numpy   # Windows
  cad-bench-venv/bin/python -m pip install build123d trimesh numpy       # macOS/Linux
  ```
- Node.js on `PATH`, only for `scripts/check_bench.py` (validates a bench
  page's recipes headlessly before you publish them).

## How to use it

See **[HOWTO.md](./HOWTO.md)** for the end-user side of the workflow above —
what you actually see and do at each step, walked through with one of the
skill's own worked examples (`models/boss_plate.py`) and its real output.

## Install

**Option A — one file.** Download [`cad-bench.skill`](./cad-bench.skill) from
this repo and drop it into a Claude Code chat. Claude will offer a **Save
skill** button on the file card; click it and you're done.

**Option B — clone it.**

```bash
git clone https://github.com/<you>/cad-bench.git ~/.claude/skills/cad-bench
```

Either way, Claude picks it up automatically the next time a request looks
like CAD/STL/3D-printing work — brackets, mounts, enclosures, adapters,
standoffs, ducts, jigs. You don't need to name the skill for it to trigger.

## What's inside

```
cad-bench/
├── SKILL.md                    the workflow Claude follows
├── scripts/
│   ├── brep.py                 build123d wrapper: selectors, safe fillet/chamfer,
│   │                           the Windows-font-crash workaround, export + gate
│   ├── verify.py               the watertight/volume/bbox gate, shared by every export
│   ├── check_bench.py          headless validator for a CAD Bench slider page
│   └── new_part.py             scaffolds a new model + matching bench recipe
├── references/
│   ├── brep.md                 operation-by-operation lookup: fillet, chamfer,
│   │                           shell, loft, selectors, the failure modes of each
│   ├── bench-artifact.md       the slider-recipe format and the Claude hand-off wiring
│   └── verification.md         why each gate exists, how to prove a selection is right
├── models/                     three worked, runnable examples
│   ├── boss_plate.py             — plain prismatic: plate, bosses, bores
│   ├── enclosure.py              — fillet → shell → chamfer, internal bosses, a port
│   └── duct.py                   — loft: round-to-rectangular transition
└── assets/
    └── bench-template.html     the CAD Bench page, ready to publish
```

## The one thing worth knowing before you use it

Fillets, chamfers, shells and lofts are **exact geometry**, not a faceted
guess — that's the entire point of building on a real kernel instead of mesh
CSG. What it *can't* do: assemblies with mates, thread modelling, sheet-metal
unfolding, FEA, or file formats other than STL/STEP. If you need those,
this skill will tell you so rather than quietly hand you something wrong.

## License

MIT — see [LICENSE](./LICENSE).
