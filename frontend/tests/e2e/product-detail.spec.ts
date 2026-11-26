import { test, expect } from '@playwright/test'

test('navigating to product detail view from catalog card and clicking CTAs', async ({ page }) => {
  // #55 visual contract: the mobile 商品詳情 must render at 390px (iPhone width).
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')

  // Switch to the mobile shell first
  const mobileSwitch = page.locator('[data-mobile-switch]')
  await expect(mobileSwitch).toBeVisible()
  await mobileSwitch.click()

  // Switch to 全部 tab to see catalog cards
  const allTab = page.locator('.m-nav-item', { hasText: '全部' })
  if (await allTab.isVisible()) {
    await allTab.click()
  }

  // Find a product card
  const card = page.locator('.m-cat-card, .m-card').first()
  await expect(card).toBeVisible()

  // Click card to open detail view
  await card.click()

  // Verify detail view renders sticky appbar & title
  const detail = page.locator('[data-detail-view]')
  await expect(detail).toBeVisible()

  const title = detail.locator('.detail-title')
  await expect(title).toContainText('商品詳情')

  // Verify product name & SKU mono caption
  await expect(detail.locator('[data-detail-name]')).toBeVisible()
  await expect(detail.locator('[data-detail-sku]')).toBeVisible()

  // #55 特價紀錄 replaced 規格摘要: the promo section renders (賣場 row + 線上
  // placeholder) and the old 規格摘要 section is gone.
  const promo = detail.locator('[data-section-promo]')
  await expect(promo).toBeVisible()
  await expect(promo).toContainText('特價紀錄')
  expect(await detail.locator('[data-section-specs]').count()).toBe(0)
  expect(await detail.locator('.detail-specs').count()).toBe(0)
  // the 線上 row shows an honest placeholder — no faked curve (series pending #56)
  await expect(detail.locator('[data-promo-online-note]')).toContainText('待補')
  // 390px: no horizontal overflow / clipping
  const scrollW = await page.evaluate(() => document.documentElement.scrollWidth)
  expect(scrollW).toBeLessThanOrEqual(391)

  // Verify CTA bar and click "下次特價通知我"
  const ctaNotify = detail.locator('[data-notify]')
  await expect(ctaNotify).toBeVisible()
  await ctaNotify.click()

  // Verify notification button text changes after click
  await expect(ctaNotify).toContainText('已設通知')

  // Click back button to return to catalog
  const backBtn = detail.locator('.detail-back')
  await expect(backBtn).toBeVisible()
  await backBtn.click()

  // Detail view should close
  await expect(detail).not.toBeVisible()
})
