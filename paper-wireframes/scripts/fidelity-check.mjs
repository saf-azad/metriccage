/**
 * Fidelity check — proves the React rebuild still matches the Claude Design export.
 *
 * The export is an `x-dc` template that needs the design runtime to render, so this
 * first rewrites it as a plain static page (same tokens, same markup, no runtime), then
 * renders both documents in Chromium and diffs them card by card.
 *
 * Options 1a and 1b are complete in the export and are diffed whole. Option 1c is
 * truncated mid-section, so only the four bands that survived are diffed. Option 1d is
 * absent from the export and has no reference to check against.
 *
 * Identical geometry can still land on a different device-pixel phase, which shows up
 * as edge anti-aliasing on every border. The strict number is reported for information;
 * the pass/fail gate is the 1px-tolerant comparison.
 *
 *   npm run check:fidelity
 */

import { chromium } from 'playwright'
import { PNG } from 'pngjs'
import { preview } from 'vite'
import { readFileSync, writeFileSync, mkdirSync, cpSync, rmSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const BUNDLE = resolve(ROOT, '../project')
const WORK = resolve(ROOT, '.fidelity')

const THRESHOLD = 12 // per-pixel RGB distance below which two pixels count as equal
const GATE = 0.05 // % of tolerant-differing pixels allowed before a card fails

// ── rebuild the export as a static reference ──────────────────────────────────
function writeReference() {
  const exportPath = `${BUNDLE}/Portfolio Wireframes.dc.html`
  if (!existsSync(exportPath)) {
    console.error(
      `\n  No design export found at ${exportPath}\n\n` +
        `  This check diffs the build against the original Claude Design bundle, which\n` +
        `  is not committed here. Put the bundle's project/ directory next to this app\n` +
        `  (so the export sits at ../project/) and run it again.\n`,
    )
    process.exit(2)
  }

  const src = readFileSync(exportPath, 'utf8')
  const inner = src.slice(src.indexOf('<x-dc>') + 6, src.lastIndexOf('</x-dc>'))
  const body = inner.slice(inner.indexOf('</helmet>') + 9)
  const style = src.slice(src.indexOf('<style>'), src.indexOf('</style>') + 8)

  rmSync(WORK, { recursive: true, force: true })
  mkdirSync(WORK, { recursive: true })
  cpSync(`${BUNDLE}/tokens`, `${WORK}/tokens`, { recursive: true })

  const links = ['fonts', 'colors', 'typography', 'geometry', 'spacing', 'motion', 'base']
    .map((t) => `<link rel="stylesheet" href="tokens/${t}.css">`)
    .join('')

  writeFileSync(
    `${WORK}/reference.html`,
    `<!DOCTYPE html><html><head><meta charset="utf-8">${links}${style}</head><body>${body}</body></html>`,
  )
}

// ── image comparison ──────────────────────────────────────────────────────────
const at = (im, x, y) => {
  const i = (im.width * y + x) << 2
  return [im.data[i], im.data[i + 1], im.data[i + 2]]
}

function compare(refPath, appPath) {
  const A = PNG.sync.read(readFileSync(refPath))
  const B = PNG.sync.read(readFileSync(appPath))
  if (A.width !== B.width || A.height !== B.height)
    return { mismatch: `ref ${A.width}x${A.height} vs app ${B.width}x${B.height}` }

  let strict = 0
  let tolerant = 0
  for (let y = 1; y < A.height - 1; y++) {
    for (let x = 1; x < A.width - 1; x++) {
      const a = at(A, x, y)
      const dist = (b) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2])
      if (dist(at(B, x, y)) > THRESHOLD) strict++
      let best = Infinity
      for (const dy of [-1, 0, 1]) for (const dx of [-1, 0, 1]) best = Math.min(best, dist(at(B, x + dx, y + dy)))
      if (best > THRESHOLD) tolerant++
    }
  }
  const n = (A.width - 2) * (A.height - 2)
  return { strict: (strict / n) * 100, tolerant: (tolerant / n) * 100 }
}

// ── capture ───────────────────────────────────────────────────────────────────
/**
 * Screenshots one card, pinned to the viewport origin.
 *
 * Cards otherwise sit at fractional page offsets, and an element screenshot rounds its
 * device rect from that offset — so two pixel-identical layouts can capture at heights
 * one pixel apart. Fixing the card to 0,0 gives both documents the same pixel phase.
 *
 * `bands` limits the capture to the first N children, which is how option 1c is
 * compared: only the bands above the truncation point exist in the export.
 */
async function shootCard(page, id, tag, bands = null) {
  const rect = await page.evaluate(
    ({ id, bands }) => {
      const card = document.querySelector(`[id="${id}"] .dv-card`)
      card.dataset.restore = card.getAttribute('style') ?? ''
      Object.assign(card.style, { position: 'fixed', top: '0px', left: '0px', zIndex: '9999' })
      const cb = card.getBoundingClientRect()
      const bottom =
        bands == null ? cb.bottom : card.children[bands - 1].getBoundingClientRect().bottom
      return { width: Math.floor(cb.width), height: Math.floor(bottom - cb.top) }
    },
    { id, bands },
  )

  await page.screenshot({ path: `${WORK}/${tag}-${id}.png`, clip: { x: 0, y: 0, ...rect } })

  await page.evaluate((id) => {
    const card = document.querySelector(`[id="${id}"] .dv-card`)
    card.setAttribute('style', card.dataset.restore)
    delete card.dataset.restore
  }, id)
}

async function capture(browser, url, tag) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } })
  // the webfont comes from a remote host; block it so both documents fall back to the
  // same local family regardless of network conditions
  await page.route('**://fonts.gstatic.com/**', (r) => r.abort())
  await page.goto(url, { waitUntil: 'networkidle' })
  await page.waitForTimeout(300)

  await shootCard(page, '1a', tag)
  await shootCard(page, '1b', tag)
  await shootCard(page, '1c', tag, 4)

  await page.close()
}

async function launch() {
  try {
    return await chromium.launch()
  } catch {
    // sandbox images ship Chromium at a versioned path Playwright may not resolve
    return await chromium.launch({
      executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
    })
  }
}

// ── run ───────────────────────────────────────────────────────────────────────
writeReference()

const server = await preview({ preview: { port: 4173, strictPort: true } })
const browser = await launch()

await capture(browser, `file://${WORK}/reference.html`, 'ref')
await capture(browser, 'http://localhost:4173/', 'app')

await browser.close()
await server.close()

const targets = [
  ['1a  broadcast scroll', '1a'],
  ['1b  dashboard', '1b'],
  ['1c  editorial (to cut)', '1c'],
]

let failed = 0
console.log('\n  card                        strict     1px-tolerant')
console.log('  ' + '─'.repeat(52))
for (const [label, key] of targets) {
  const r = compare(`${WORK}/ref-${key}.png`, `${WORK}/app-${key}.png`)
  if (r.mismatch) {
    console.log(`  ${label.padEnd(26)} SIZE MISMATCH  ${r.mismatch}`)
    failed++
    continue
  }
  const ok = r.tolerant <= GATE
  if (!ok) failed++
  console.log(
    `  ${label.padEnd(26)} ${r.strict.toFixed(3).padStart(6)}%   ${r.tolerant.toFixed(3).padStart(6)}%   ${ok ? 'ok' : 'FAIL'}`,
  )
}
console.log(
  `\n  1d has no reference — it is absent from the export and was reconstructed.\n` +
    `  ${failed ? `${failed} card(s) failed` : 'all cards match the export'}\n`,
)
process.exit(failed ? 1 : 0)
