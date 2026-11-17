// gate_sloplint.mjs — CI "anti-AI-slop" design gate (issue #38).
//
// Runs the vendored Hallmark checker (Nutlope/hallmark, MIT) against the
// frontend and BLOCKS the build on enforceable gates. Sloplint is a
// zero-dependency Node 18+ tool; the whole anti-slop vocabulary lives in
// its `references/gates.md` (human mirror: pipeline/design-anti-slop-gates.md).
//
// We do NOT adopt Hallmark wholesale: three gate families are DEFERRED by
// design (documented in issue #38) and excluded from the blocker. Everything
// else that is a FAIL is a blocker — so new Floor/Reflex regressions still RED.
//
// EXCLUDE = {
//   '20'  Hallmark stamp — we keep design decisions in design.md + pipeline/
//         instead of a foreign Hallmark CSS stamp; a stamp cascades 5 more
//         Floor gates (7/23/42/44/65). Deciding "do we adopt Hallmark fully?"
//         is a separate, focused design decision.
//   '30a' emoji-in-heading — collides with the tested #24 relabel invariant
//         (🎯 = manual target list, ⚙ = auto threshold gate, 🎯 exactly once
//         in App.vue, 0 in the editor). Migrating to inline-SVG icons and
//         retargeting those tests is a dedicated follow-up PR.
//   '48'  colour literal in index.html only — the body bg/text there is a
//         flash-fill that mirrors --bg/--text; it is kept as
//         var(--token, #fallback) so first paint is dark before the token
//         sheet loads. Raw hex inside .vue components is ALREADY blocked by the
//         separate CSS-token guard in ci.yml, so excluding 48 here loses no
//         coverage of the real problem (stray hex in components).
// }
import { spawnSync } from 'node:child_process'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const EXCLUDE = new Set(['20', '30a', '48'])

// Reuse the node that is running this script, so it runs in exactly the CI node.
const r = spawnSync(
  process.execPath,
  [resolve(__dirname, 'sloplint.mjs'), '.', '--scope', 'component', '--json'],
  { cwd: join(__dirname, '..'), encoding: 'utf8', maxBuffer: 1 << 23 },
)

if (r.stderr && r.stderr.trim()) process.stderr.write(r.stderr)

let findings = []
try {
  const d = JSON.parse(r.stdout || '{}')
  findings = (d && d.findings) || []
} catch (e) {
  console.error('gate_sloplint: could not parse sloplint output:', e.message)
  console.error((r.stdout || '(empty)').slice(0, 400))
  process.exit(2)
}

const fails = findings.filter((f) => f.grade === 'FAIL')
const bad = fails.filter((f) => !EXCLUDE.has(f.gate))
const deferred = fails.filter((f) => EXCLUDE.has(f.gate))

console.log(
  `sloplint: ${fails.length} FAIL total → ${bad.length} enforceable (blocking), ` +
    `${deferred.length} deferred (excluded: ${[...new Set(deferred.map((f) => f.gate))].join(',') || 'none'})`,
)
for (const f of bad) {
  console.log(`  FAIL ${f.gate} ${f.file}:${f.line}  ${f.evidence}  → ${f.fix}`)
}
if (bad.length === 0) {
  console.log('✅ anti-AI-slop guard passed (enforceable gates green).')
} else {
  console.error(`❌ ${bad.length} enforceable Floor/Reflex violation(s). See the FAIL lines above.`)
}
process.exit(bad.length ? 1 : 0)
