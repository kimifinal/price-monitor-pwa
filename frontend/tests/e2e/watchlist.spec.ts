import { test, expect } from '@playwright/test'

// E2E regression — the SAME "guard-rail" pattern from mini-calculator.
// A watched item added at/below its target must render a hot alert card.
// If the alert decision (monitor.js) ever breaks, THIS assertion fails.
//
// A freshly-added item starts its price at its target (price === target), so
// shouldAlert() is true; the card renders hot. It also appears in the watch
// list, so use .first()/scoped locators to satisfy Playwright strict mode.
test('an item added at its target renders a hot alert card', async ({ page }) => {
  await page.goto('/')

  // Add via the real form (the path a user takes).
  await page.getByPlaceholder('品名（如 Chiikawa 徽章）').fill('測試徽章')
  await page.getByPlaceholder('目標價').fill('100')
  await page.getByRole('button', { name: '加入追蹤' }).click()

  // It should now alert (100 <= 100) in the alerts panel.
  await expect(page.locator('.alerts')).toBeVisible()
  await expect(
    page.locator('.alerts').getByRole('heading', { name: '測試徽章' }).first(),
  ).toBeVisible()
  await expect(page.locator('.item-card[data-alert="true"]').first()).toBeVisible()

  // And the delete button (first one) removes it from the alerts panel.
  await page.locator('.alerts').getByRole('button', { name: '刪除' }).first().click()
  await expect(page.locator('.alerts')).toHaveCount(0)
})
