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
