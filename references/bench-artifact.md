# The CAD Bench artifact

A single published Artifact, `<title>CAD Bench</title>`, holding a picker of
parts. Each part is a self-contained recipe object. The page renders sliders,
live derived values, pass/fail constraint checks, and an SVG orthographic
preview -- and can write the current values into its own store for Claude to
read back.

`assets/bench-template.html` is this page with one example part (`boss-plate`)
already wired. Publish it as-is on first use; extend `PARTS` thereafter.

## Contents

1. Publishing and the `db` capability
2. The PART recipe object
3. `derive` / `cards` / `checks` / `draw` in detail
4. The SVG helper vocabulary
5. The handoff: writing `bench/<part>` and reading it back
6. Extending the shared page without breaking it

---

## 1. Publishing and the `db` capability

The page calls `window.claude.use("db")`. For that to resolve, publish with
the capability declared:

```
Artifact  file_path:<bench.html>  title:"CAD Bench"  favicon:"📐"
          capabilities: { "db": {} }
```

Read the `artifact-capabilities` skill first for the current contract. If the
capability is not granted in a given context the page still works -- the
"Hand these to Claude" button hides and the user falls back to **Copy
constants** (a plain text block) which you paste in yourself.

On every later republish to the same URL, **omit `favicon`** and keep the
`title` stable, or the artifact reads as a different page.

## 2. The PART recipe object

```js
"boss-plate": {
  label: "Boss plate",                    // picker button text
  file:  "models/boss_plate.py",          // shown on the page; the model it pairs with
  note:  "Why the dimensions are what they are — the reasoning a reviewer needs.",
  params: [
    // one row per slider. id === the model PARAMS key. fs is optional and only
    // used to emit a `const` block for copy-paste; omit it and the value is
    // still handed over, just not printed in the consts pane.
    {id:"plate_x", fs:"PLATE_X", u:"MM",  g:"Plate", label:"Long side",  min:40, max:200, step:1,  val:60},
    {id:"plate_y", fs:"PLATE_Y", u:"MM",  g:"Plate", label:"Short side", min:30, max:160, step:1,  val:40},
    {id:"plate_t", fs:"PLATE_T", u:"MM",  g:"Plate", label:"Thickness",  min:2,  max:8,   step:.5, val:3},
    {id:"inset",   fs:"INSET",   u:"MM",  g:"Plate", label:"Hole inset", min:3,  max:20,  step:.5, val:8},
    {id:"boss_d",  fs:"BOSS_D",  u:"MM",  g:"Boss",  label:"Diameter",   min:5,  max:24,  step:.5, val:10},
    {id:"boss_h",  fs:"BOSS_H",  u:"MM",  g:"Boss",  label:"Height",     min:4,  max:40,  step:1,  val:12},
    {id:"bore_d",  fs:"BORE_D",  u:"MM",  g:"Boss",  label:"Bore",       min:2,  max:10,  step:.1, val:4},
  ],
  derive(p) { /* returns an object of computed values, see below */ },
  cards:  d => [ ["Boss wall", d.boss_wall.toFixed(2)], /* ... */ ],
  checks(p, d) { /* returns [ [ok, label, detail], ... ] */ },
  draw(p, d) { /* returns an SVG string */ },
}
```

`g` groups sliders under a heading. `u` is `"MM"` or `"DEG"` and controls the
unit shown and the `* MM` / `* DEG` suffix in the consts pane. `step` sets the
slider granularity -- match it to what you can actually hold in a print
(0.1 mm for fits, 1 mm for gross size, 0.5-1° for angles).

## 3. derive / cards / checks / draw

**`derive(p)` -> object.** Pure function of the slider values. Put every
computed quantity here -- radii, positions, wall thicknesses, angles -- so
`cards`, `checks` and `draw` all read the same numbers. This should mirror the
model's own `derive(P)` so the page and the STL agree. JS getters are fine for
chained derivations.

**`cards(d)` -> `[[label, text], ...]`.** The read-out grid under the drawing.
Show the numbers a reviewer checks first: key radii, volume, critical gaps.

**`checks(p, d)` -> `[[ok, label, detail], ...]`.** The heart of the page.
Each row is a boolean, a short claim, and a measured detail string. Write one
per binding constraint:

```js
checks(p, d) {
  const tip = p.bore_d ? (p.inset - p.bore_d / 2) : 0;
  return [
    [d.boss_wall >= 2, "Boss survives the insert",
      d.boss_wall.toFixed(2) + " mm wall, want 2"],
    [p.boss_h > p.plate_t + 3, "Boss stands proud of the plate",
      (p.boss_h - p.plate_t).toFixed(1) + " mm"],
    [tip >= 2, "Bore clears the plate edge", tip.toFixed(2) + " mm"],
    [2 * p.inset < Math.min(p.plate_x, p.plate_y), "Bosses do not overlap",
      "centres " + (Math.min(p.plate_x, p.plate_y) - 2 * p.inset).toFixed(1) + " mm apart"],
  ];
}
```

A `true` literal as the first element makes an always-green informational row
("Opening is the body's own outline, 15.5 × 12.5 plus 0.5") -- useful for
stating a design decision inline.

**The `d.` / `p.` trap.** Slider values live on `p`; computed values live on
`d`. Writing `d.boss_d` when `boss_d` is a slider yields `undefined`. In an
arithmetic context that becomes `NaN` and every comparison against it is
`false`; in a bare comparison like `undefined >= 2` it is simply `false` with
no `NaN` anywhere. Either way the row goes **red and looks like a genuine
constraint failure**, so you tune sliders trying to fix a typo.

The template's `render()` labels a `NaN` row "CHECK IS BROKEN", but that only
catches the arithmetic half. Catching the *read* is the reliable detection, so
always run the shipped checker before publishing:

```
python scripts/check_bench.py <bench.html>
```

It evaluates every recipe at defaults and at every slider extreme, and traps
reads of keys that do not exist on the object being read -- the only reliable
detection for this class. It exits non-zero on any problem.

**`draw(p, d)` -> SVG string.** At least one orthographic view (top, or a
section) with the driving dimensions and the constrained features marked.
Scale to fit the `viewBox` (`0 0 620 400` in the template). This is a
sanity-check sketch, not a render -- its job is to make a gross error
obvious (a boss off the plate, a wall on the wrong side).

## 4. SVG helper vocabulary

The template defines these at the top of `<script>`; use them in `draw`:

| helper | makes |
|---|---|
| `S(x,y)` | `"x,y"` point string, 1 dp |
| `pg(pts, attr)` | `<polygon>` from `[[x,y],...]`; default fill = part colour |
| `rc(x,y,w,h, attr)` | `<rect>` (w/h may be negative) |
| `ci(x,y,r, attr)` | `<circle>`; default = void colour (a hole) |
| `ln(x1,y1,x2,y2)` | dashed construction line |
| `tx(x,y,s, size)` | small label text |
| `cap(x,y,s)` | tracked-out caption (view title) |
| `A(extra)` / `V` / `G` | attribute strings: part fill / void fill / ghost outline |

Colours come from CSS variables that already adapt to light/dark
(`--part`, `--part-line`, `--void`, `--rule`, `--warn`, `--ok`). Never
hard-code a hex value in `draw`.

## 5. The handoff

The page's sliders live only in the browser. The handoff copies them into the
artifact's store where `read_db` can reach them.

**On "Hand these to Claude"** the page runs:

```js
DB.doc("bench/" + KEY).set({
  part:   KEY,             // e.g. "boss-plate"
  label:  part.label,
  file:   part.file,
  params: vals(),          // { plate_x: 62, plate_y: 40, ... }  <- what you want
  consts: <the const block text>,
  savedAt: new Date().toISOString(),
});
```

A live snapshot listener shows "Claude last received this part at HH:MM:SS"
so the user can see whether the sliders in front of them have been sent.

**To read it back:**

```
Artifact  action:read_db  url:<artifact-url>  db_op:get
          collection:"bench"  doc_id:"<part>"
```

Returns the document. Take `params`, write it to
`models/<part>.params.json`, and the model's `__main__` picks it up. If
`savedAt` is older than your last delivery, the user hasn't re-handed --
ask before regenerating.

`bench/` is a shared collection; each part is one document, overwritten on
each hand-off. Nothing else writes there.

## 6. Extending the shared page

1. `Artifact action:read url:<artifact-url>` to get the current HTML into a
   local file.
2. Add your new key to the `PARTS` object. Leave `let KEY = "<first-part>"`
   pointing at whatever it was -- the picker lets the user switch.
3. Keep the existing parts byte-for-byte. They have their own `bench/<part>`
   rows and users may be mid-tweak.
4. Republish to the **same URL** (`Artifact file_path:<file> url:<artifact-url>`),
   no `favicon`, same `title`.
5. If you changed a part's `params` (added/renamed a slider), update that
   part's model `PARAMS` in the same change, and note it to the user -- their
   stored `bench/<part>` row and their `localStorage` slider state are now
   partly stale.
