#!/usr/bin/env python3
"""
check_bench.py -- validate a CAD Bench page's PARTS recipes without a browser.

Recipe bugs do not throw; they render. A check that reads `d.plate_x` when
`plate_x` is a slider yields NaN, every comparison against NaN is false, and
the row turns RED exactly like a real constraint failure -- so you tune
sliders trying to fix a typo. This catches that class before publishing.

    python scripts/check_bench.py assets/bench-template.html

For each part it evaluates derive/cards/checks/draw at the default values,
then sweeps every slider to its min and its max. Reports NaN, non-boolean
check verdicts, and exceptions. Exits non-zero if anything failed.

Requires node on PATH (only for running the page's own JavaScript).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');   // argv[1] is this harness
const m = src.match(/<script>([\s\S]*)<\/script>/);
if (!m) { console.log(JSON.stringify({fatal: "no <script> block found"})); process.exit(0); }

// Minimal DOM/browser stubs: enough for the page's top-level setup to run.
const stubEl = () => ({innerHTML:'', textContent:'', className:'', value:'0',
                       hidden:false, disabled:false, style:{},
                       addEventListener(){}, querySelectorAll(){return [];}});
global.document = {getElementById: stubEl, querySelectorAll(){return [];}};
global.localStorage = {getItem(){return '{}';}, setItem(){}};
global.window = {};
global.navigator = {};

// ---- SVG layout check --------------------------------------------------
// Recipe bugs of THIS class render fine and throw nothing: a caption text
// placed at a fixed (x,y) that a later-computed shape grows over, or two
// views whose regions were never given disjoint pixel bounds, so one is
// drawn straight on top of the other. Approximate bounding boxes (real
// text metrics need a real layout engine, which this harness deliberately
// has none of -- it stays a fast headless check) are precise enough to
// catch "mostly covered", which is the failure mode that actually makes a
// drawing unreadable.
function parseAttrs(str) {
  const o = {}; const re = /([\w:-]+)\s*=\s*"([^"]*)"/g; let m;
  while ((m = re.exec(str))) o[m[1]] = m[2];
  return o;
}
function bboxOf(tag, attrsStr, inner) {
  const a = parseAttrs(attrsStr);
  if (tag === 'rect') {
    const x = +a.x, y = +a.y, w = +a.width, h = +a.height;
    if ([x, y, w, h].some(Number.isNaN)) return null;
    return {x0: x, y0: y, x1: x + w, y1: y + h, fill: a.fill};
  }
  if (tag === 'circle') {
    const cx = +a.cx, cy = +a.cy, r = +a.r;
    if ([cx, cy, r].some(Number.isNaN)) return null;
    return {x0: cx - r, y0: cy - r, x1: cx + r, y1: cy + r, fill: a.fill};
  }
  if (tag === 'polygon') {
    const pts = (a.points || '').trim().split(/\s+/).filter(Boolean)
      .map(p => p.split(',').map(Number));
    if (!pts.length) return null;
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    return {x0: Math.min(...xs), y0: Math.min(...ys),
            x1: Math.max(...xs), y1: Math.max(...ys), fill: a.fill};
  }
  if (tag === 'path') {
    // Every point-bearing path in this format is built from the shared
    // S(x,y) -> "x,y" helper, comma-joined -- unlike the space-separated
    // radius/rotation/flag numbers an arc command also carries. Matching
    // only comma-joined pairs pulls out exactly the path's real points.
    const pairs = [...(a.d || '').matchAll(/(-?\d+\.?\d*),(-?\d+\.?\d*)/g)]
      .map(mm => [+mm[1], +mm[2]]);
    if (!pairs.length) return null;
    const xs = pairs.map(p => p[0]), ys = pairs.map(p => p[1]);
    return {x0: Math.min(...xs), y0: Math.min(...ys),
            x1: Math.max(...xs), y1: Math.max(...ys), fill: a.fill};
  }
  if (tag === 'text') {
    const x = +a.x, y = +a.y, fs = +(a['font-size'] || 11);
    if ([x, y].some(Number.isNaN)) return null;
    const charW = fs * 0.56;   // rough average glyph width, IBM Plex Sans
    const w = (inner || '').length * charW;
    return {x0: x, y0: y - fs * 0.82, x1: x + w, y1: y + fs * 0.28, text: inner};
  }
  return null;
}
function bboxArea(b) { return Math.max(0, b.x1 - b.x0) * Math.max(0, b.y1 - b.y0); }
function bboxIntersect(a, b) {
  const iw = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0);
  const ih = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
  return (iw <= 0 || ih <= 0) ? 0 : iw * ih;
}
function checkLayout(svg) {
  const problems = [];
  const els = [];
  const re = /<(rect|circle|polygon|path|text)\s+([^>]*?)(?:\/>|>([^<]*)<\/text>)/g;
  let m;
  while ((m = re.exec(svg))) {
    const b = bboxOf(m[1], m[2], m[3]);
    if (b) els.push(Object.assign({tag: m[1]}, b));
  }
  const texts = els.filter(e => e.tag === 'text');
  const shapes = els.filter(e => e.tag !== 'text' && e.fill && e.fill !== 'none');
  for (const t of texts) {
    const tArea = bboxArea(t);
    if (tArea <= 0) continue;
    for (const s of shapes) {
      const ov = bboxIntersect(t, s);
      if (ov > 0.35 * tArea)
        problems.push('text "' + (t.text || '').slice(0, 28) + '" mostly covered by a <'
          + s.tag + '> (' + Math.round(100 * ov / tArea) + '% overlap) -- unreadable');
    }
  }
  // Two SOLID ("part"-fill) shapes heavily overlapping is the two-views-
  // drawn-in-the-same-region bug. A hole in a boss is NOT this: holes are
  // void-fill, so restricting to part-vs-part avoids flagging that.
  //
  // FULL CONTAINMENT IS A SEPARATE, LEGITIMATE PATTERN, not this bug --
  // found the hard way: a boss drawn solid-on-solid standing on a section's
  // own solid wall (both part-fill, by design, to show it standing proud)
  // sits at ~100% overlap of its own (smaller) area, same as tof_wedge's
  // real two-views-collided bug once was at 63%. The two are NOT the same
  // shape of defect: a real view collision leaves each shape SOME area
  // outside the other (neither fully contains the other); a boss standing
  // on a wall has the smaller shape's bbox ENTIRELY inside the larger's.
  // Distinguish by containment, not just overlap fraction -- flag the
  // partial-overlap band (a real collision) and skip near-full containment
  // (a legitimate nested feature).
  const solids = shapes.filter(s => /var\(--part\)/.test(s.fill || ''));
  for (let i = 0; i < solids.length; i++)
    for (let j = i + 1; j < solids.length; j++) {
      const a = solids[i], b = solids[j];
      const smaller = Math.min(bboxArea(a), bboxArea(b));
      if (smaller <= 0) continue;
      const ov = bboxIntersect(a, b);
      const frac = ov / smaller;
      if (frac > 0.3 && frac <= 0.95)
        problems.push('two solid shapes overlap ' + Math.round(100 * frac)
          + '% of the smaller one -- looks like two views sharing one region');
    }
  return problems;
}

const out = {parts: [], fatal: null};
try {
  const probe = `
    ;(function(){
      for (const key of Object.keys(PARTS)) {
        const P = PARTS[key];
        const rec = {key, file: P.file || null, label: P.label || null,
                     params: P.params.length, problems: []};
        const base = {}; P.params.forEach(q => base[q.id] = q.val);

        const ids = new Set(P.params.map(q => q.id));
        const dup = P.params.map(q=>q.id).filter((v,i,a)=>a.indexOf(v)!==i);
        if (dup.length) rec.problems.push('duplicate slider ids: ' + dup.join(','));
        for (const q of P.params) {
          if (!/^[a-z_][a-z0-9_]*$/.test(q.id))
            rec.problems.push('slider id not lower_snake_case: ' + q.id);
          if (!(q.val >= q.min && q.val <= q.max))
            rec.problems.push('default out of range: ' + q.id);
          if (!(q.step > 0)) rec.problems.push('non-positive step: ' + q.id);
        }

        // Reading a key that does not exist is THE bug of this file format:
        // d.plate_x when plate_x is a slider gives undefined, and
        // "undefined >= 2" is a perfectly ordinary false -- no NaN, no throw,
        // just a row that goes red and looks like a real constraint failure.
        // Catching the READ is the only reliable detection.
        // (No backticks in here -- this block lives inside a template literal.)
        const watch = (obj, sink, tag) => new Proxy(obj, {
          get(t, k) {
            if (typeof k === 'string' && !(k in t) && k !== 'then'
                && k !== 'toJSON' && k !== 'inspect')
              sink.add(tag + '.' + k);
            return t[k];
          }
        });

        const evalAt = (p, where) => {
          const missing = new Set();
          let d;
          try { d = P.derive(watch(p, missing, 'p')); }
          catch (e) { rec.problems.push(where + ': derive threw ' + e.message); return; }
          const dRaw = d;
          d = watch(d, missing, 'd');
          p = watch(p, missing, 'p');
          const reportMissing = () => {
            for (const k of missing)
              rec.problems.push(where + ': read undefined ' + k
                                + ' (wrong object -- sliders are on p, computed on d)');
          };
          try {
            const cards = P.cards(d);
            for (const c of cards)
              if (String(c[1]).includes('NaN') || String(c[1]).includes('undefined'))
                rec.problems.push(where + ': card "' + c[0] + '" = ' + c[1]);
          } catch (e) { rec.problems.push(where + ': cards threw ' + e.message); }
          try {
            const rows = P.checks(p, d);
            for (const r of rows) {
              if (typeof r[0] !== 'boolean')
                rec.problems.push(where + ': check "' + r[1] + '" verdict is ' + typeof r[0]);
              if (String(r[2]).includes('NaN') || String(r[2]).includes('undefined'))
                rec.problems.push(where + ': check "' + r[1] + '" detail = ' + r[2]);
            }
            if (where === 'defaults') rec.checks = rows.length,
                                      rec.failing = rows.filter(r=>!r[0]).map(r=>r[1]);
          } catch (e) { rec.problems.push(where + ': checks threw ' + e.message); }
          try {
            const svg = P.draw(p, d);
            if (String(svg).includes('NaN'))
              rec.problems.push(where + ': draw() emitted NaN into the SVG');
            if (where === 'defaults') rec.svg = String(svg).length;
            for (const prob of checkLayout(String(svg)))
              rec.problems.push(where + ': ' + prob);
          } catch (e) { rec.problems.push(where + ': draw threw ' + e.message); }
          reportMissing();
        };

        evalAt(base, 'defaults');
        for (const q of P.params)
          for (const v of [q.min, q.max])
            evalAt(Object.assign({}, base, {[q.id]: v}), q.id + '=' + v);

        out.parts.push(rec);
      }
    })();
  `;
  eval(m[1] + probe);
} catch (e) { out.fatal = e.message; }
console.log(JSON.stringify(out));
"""


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: check_bench.py <bench.html>")
    page = os.path.abspath(sys.argv[1])
    if not os.path.exists(page):
        sys.exit(f"no such file: {page}")
    if not shutil.which("node"):
        sys.exit("check_bench.py needs node on PATH to run the page's own JS")

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(HARNESS)
        harness = fh.name
    try:
        r = subprocess.run(["node", harness, page], capture_output=True,
                           text=True, timeout=120)
    finally:
        os.unlink(harness)

    if r.returncode != 0:
        print(r.stderr.strip()[:2000])
        sys.exit("node failed to run the page")
    try:
        data = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        print(r.stdout[:2000], r.stderr[:2000])
        sys.exit("could not parse harness output")

    if data.get("fatal"):
        sys.exit(f"page script failed: {data['fatal']}")

    bad = 0
    for p in data["parts"]:
        n = len(p["problems"])
        bad += n
        status = "OK  " if n == 0 else "FAIL"
        print(f"{status} {p['key']:<20} sliders={p['params']:<3} "
              f"checks={p.get('checks','?'):<3} svg={p.get('svg','?')} "
              f"file={p['file']}")
        for f in p.get("failing", []):
            print(f"       red at defaults: {f}")
        for problem in p["problems"][:12]:
            print(f"       ! {problem}")
        if n > 12:
            print(f"       ... and {n - 12} more")

    print(f"\n{len(data['parts'])} part(s), {bad} problem(s)")
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
