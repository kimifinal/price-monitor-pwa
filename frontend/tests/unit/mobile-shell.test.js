import { describe, it, expect, afterAll, beforeAll, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import MobileApp from '../../src/components/mobile/MobileApp.vue'
import MvmMobileCatalog from '../../src/components/mobile/MvmMobileCatalog.vue'
import NewArrivalsMobile from '../../src/components/mobile/NewArrivalsMobile.vue'
import CatalogMobile from '../../src/components/mobile/CatalogMobile.vue'

// #48 — the warm e-commerce mobile shell (案 B / #49).
// The and 5-tab 底部導航: 特價 / 新品 / 追蹤 / 全部 / 我的.
// The 特價 tab renders the warm MVM 檔期 view (MvmMobileCatalog);
// the 新品 tab renders the discovery NewArrivalsMobile;
// the 全部 tab renders the 全庫 CatalogMobile;
// the 追蹤 / 我的 tabs are honest placeholders.
// The shell coexists with the dark PWA (App.vue mounts it as an on-demand overlay), so this
// test asserts the shell's own contract in isolation.
//
// The five 底部導航 tab keys / labels, in order.
const KEYS = ['deal', 'new', 'watch', 'all', 'me']
const LABELS = ['特價', '新品', '追蹤', '全部', '我的']

const mountShell = () => mount(MobileApp)

// The catalog is a 2026-11-16 snapshot. The 已過期 檔期 filter (activePeriods)
// drops only 檔期 whose 結束日 has passed; the 11/20 檔期 slips past a later
// "today". Pin the clock to the snapshot date so the full 7-檔期 assertion stays
// deterministic instead of rotating with the wall clock. (Only the Date clock is
// pinned here; microtask flushes from .trigger() still resolve.)
beforeAll(() => {
  vi.useFakeTimers()
  vi.setSystemTime(2026, 10, 16, 12, 0, 0)
})
afterAll(() => {
  vi.useRealTimers()
})

describe('MobileApp.vue — 暖色 shell + 5-tab 導航 (特價/新品/追蹤/全部/我的), 特價 default', () => {
  it('shows the 品牌 好市多雷達 in the top bar', () => {
    const w = mountShell()
    expect(w.text()).toContain('好市多雷達')
    expect(w.find('.m-brand-name').exists()).toBe(true)
  })

  it('renders all 5 底部導航 tabs in order (特價/新品/追蹤/全部/我的)', () => {
    const w = mountShell()
    expect(w.findAll('.m-tab')).toHaveLength(5)
    expect(w.findAll('.m-tab-label').map((n) => n.text())).toEqual(LABELS)
  })

  it('opens on 特價 by default — the 特價 tab (index 0) is active and the MVM 檔期 view is on screen', () => {
    const w = mountShell()
    // the 特價 tab (index 0) carries is-active
    expect(w.findAll('.m-tab')[0].classes()).toContain('is-active')
    // the MVM 檔期 view is mounted: its 7 檔期 chips + catalog are present
    expect(w.findComponent(MvmMobileCatalog).exists()).toBe(true)
    expect(w.findAll('.mvm-chip')).toHaveLength(7) // Kimi 11-22: 黑色購物週 added
    // and this default screen is NOT a placeholder
    expect(w.find('.m-placeholder').exists()).toBe(false)
  })

  it('the 特價 tab has NO 賣場/線上 segmented toggle (that is the 全部 view, not 檔期)', () => {
    const w = mountShell()
    expect(w.find('[data-buyonline-toggle]').exists()).toBe(false)
    expect(w.find('.mvm-seg').exists()).toBe(false)
  })

  it('clicking 追蹤 / 我的 each shows an honest placeholder, not the MVM view', async () => {
    const w = mountShell()
    const tabs = w.findAll('.m-tab')
    // 0=特價 (MVM view), 1=新品 (NewArrivals), 3=全部 (catalog) — placeholders are
    // 2=追蹤 and 4=我的.
    for (const idx of [2, 4]) {
      await tabs[idx].trigger('click')
      const ph = w.find('.m-placeholder')
      expect(ph.exists()).toBe(true)
      expect(ph.attributes('data-tab')).toBe(KEYS[idx])
      expect(ph.text()).toContain('開發中')
      // switching to a placeholder unmounts the MVM catalog
      expect(w.findComponent(MvmMobileCatalog).exists()).toBe(false)
      expect(w.findAll('.mvm-chip')).toHaveLength(0)
      // the clicked tab is now active
      expect(w.findAll('.m-tab')[idx].classes()).toContain('is-active')
    }
  })

  it('clicking 新品 (index 1) renders the discovery NewArrivalsMobile, not a placeholder', async () => {
    const w = mountShell()
    await w.findAll('.m-tab')[1].trigger('click') // 新品 (index 1)
    // the 新品 view mounts (it is NOT the placeholder)
    expect(w.findComponent(NewArrivalsMobile).exists()).toBe(true)
    expect(w.find('.m-placeholder').exists()).toBe(false)
    // it renders the 4 時段 chips + a カテゴリ row
    expect(w.findAll('.na-period')).toHaveLength(4)
    expect(w.findAll('.na-cat-chip').length).toBeGreaterThan(1) // 全部 + the real tags
    expect(w.text()).toContain('新品')
    // switching away to 追蹤 unmounts it again
    await w.findAll('.m-tab')[2].trigger('click') // 追蹤 (index 2)
    expect(w.findComponent(NewArrivalsMobile).exists()).toBe(false)
  })

  it('clicking 全部 shows the 全庫 catalog view (#50) with a 賣場/線上 toggle, not a placeholder', async () => {
    const w = mountShell()
    await w.findAll('.m-tab')[3].trigger('click') // 全部 (index 3)
    // the 全庫 catalog view mounts and is NOT the placeholder
    expect(w.findComponent(CatalogMobile).exists()).toBe(true)
    expect(w.find('.m-placeholder').exists()).toBe(false)
    // the 賣場/線上 sliding toggle is present; 賣場 is active by default
    expect(w.find('[data-buyonline-toggle]').exists()).toBe(true)
    expect(w.find('[data-seg="store"]').classes()).toContain('is-active')
    // the count bar + the first page of warm cards render
    expect(w.find('[data-cat-count]').exists()).toBe(true)
    expect(w.findAll('.m-cat-card').length).toBeGreaterThan(0)
    // clicking 線上 flips the toggle to the 全庫 (online) mode
    await w.find('[data-seg="online"]').trigger('click')
    expect(w.find('[data-seg="online"]').classes()).toContain('is-active')
    expect(w.find('[data-seg="store"]').classes()).not.toContain('is-active')
  })

  it('clicking 特價 from a placeholder brings the MVM 檔期 view back', async () => {
    const w = mountShell()
    await w.findAll('.m-tab')[2].trigger('click') // 追蹤 placeholder (index 2)
    expect(w.find('.m-placeholder').exists()).toBe(true)
    await w.findAll('.m-tab')[0].trigger('click') // back to 特價 (index 0)
    expect(w.findComponent(MvmMobileCatalog).exists()).toBe(true)
    expect(w.findAll('.mvm-chip')).toHaveLength(7) // Kimi 11-22: 黑色購物週 added
    expect(w.find('.m-placeholder').exists()).toBe(false)
  })

  it('the search input and nav buttons are a11y-labelled and emoji-free', () => {
    const w = mountShell()
    expect(w.find('.m-search').exists()).toBe(true)
    expect(w.find('.m-search').attributes('aria-label')).toContain('搜尋')
    // each nav button carries an aria-label equal to its 中文 tab name
    for (const btn of w.findAll('.m-tab')) {
      expect(btn.attributes('aria-label')).toMatch(/特價|新品|追蹤|全部|我的/)
    }
    // no emoji glyph anywhere in the shell (sloplint gate 30a is enforced in CI)
    expect(w.text()).not.toMatch(/\p{Extended_Pictographic}/u)
  })

  it('mounts the warm MVM 檔期 view with a non-empty item list on the default 檔期', () => {
    const w = mountShell()
    expect(w.findComponent(MvmMobileCatalog).exists()).toBe(true)
    // the default active 檔期 (first 檔期 with products) renders its full list
    expect(w.findAll('.m-card').length).toBeGreaterThan(0)
  })
})
