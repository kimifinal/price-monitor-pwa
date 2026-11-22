import { chromium } from '@playwright/test'

const url = process.argv[2]
const out = process.argv[3]

const b = await chromium.launch({ headless: true })
const page = await (await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true })).newPage()
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 })
await page.waitForTimeout(4500)

// --- DARK view first (default): is a dark .mvm-chip still wrap (NOT cascaded warm)? ---
const darkChips = await page.$$eval('.mvm-chip', (els) =>
  els.slice(0, 3).map((e) => {
    const cs = getComputedStyle(e)
    return { flexWrap: cs.flexWrap, bgRGB: cs.backgroundColor, rounded: cs.borderRadius }
  })
)

// --- enter the warm mobile shell by clicking the floating toggle ---
const sw = await page.$('[data-mobile-switch]')
await sw.click()
await page.waitForTimeout(2500)

const shell = await page.evaluate(() => {
  // find the mobile MVM chip row in the warm shell
  const cn = document.querySelector('[data-v-513d5ffb].mvm-chips') ||
    Array.from(document.querySelectorAll('.mvm-chips')).find((c) => getComputedStyle(c).flexWrap === 'nowrap')
  const chips = cn ? Array.from(cn.children) : []
  const rows = [...new Set(chips.map((c) => c.offsetTop))].length
  const canScrollX = cn ? cn.scrollWidth > cn.clientWidth + 4 : false
  // float position
  const btn = document.querySelector('[data-mobile-switch]')
  const cs = btn ? getComputedStyle(btn) : null
  const onClass = btn ? btn.classList.contains('is-on') : false
  // tabbar right edge
  const tab = document.querySelector('.m-tabbar')
  const tRect = tab ? tab.getBoundingClientRect() : null
  return {
    chipCount: chips.length,
    chipFlexWrap: cn ? getComputedStyle(cn).flexWrap : null,
    rows, canScrollX,
    chipRadius: chips[0] ? getComputedStyle(chips[0]).borderRadius : null,
    floatText: btn ? btn.textContent.trim() : null,
    floatIsOn: onClass,
    floatBottomPx: cs ? cs.bottom : null,
    floatRightPx: cs ? cs.right : null,
    tabbarRect: tRect ? { top: Math.round(tRect.top), height: Math.round(tRect.height) } : null,
    floatBottomOverlapsTab: tRect && cs ? (parseFloat(cs.bottom) < (window.innerHeight - tRect.top) + 2 && parseFloat(cs.right) === 16) : null,
  }
})

await page.screenshot({ path: out, fullPage: false })
console.log('DARK_chips=' + JSON.stringify(darkChips))
console.log('SHELL=' + JSON.stringify(shell, null, 0))
await b.close()
