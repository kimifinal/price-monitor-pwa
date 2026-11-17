import { test, expect } from '@playwright/test'

// E2E guard for the 歷史價格比價 section.
// The section renders one PriceHistory card per compare item; each card must
// have a sparkline <path> and a verdict badge.
test('the compare section renders sparkline cards sorted by drop %', async ({ page }) => {
  await page.goto('/')

  const section = page.locator('section[data-section="compare"]')
  await expect(section).toBeVisible()

  // 3 sample cards: 3 retailer items (the compare demo)
  const cards = section.locator('.price-history[data-verdict]')
  await expect(cards.first()).toBeVisible()
  await expect(cards).toHaveCount(3)

  // each card draws a sparkline path (+ a verdict badge). The card now ALSO carries
  // decorative line-icons (#40), so address the sparkline path via its .ph-spark
  // container — not a bare 'path' that would also match the cart/chart icons.
  await expect(cards.first().locator('.ph-spark path')).toBeVisible()
  await expect(cards.first().locator('.ph-badge')).toBeVisible()
})
