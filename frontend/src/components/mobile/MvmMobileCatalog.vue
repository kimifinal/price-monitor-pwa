<script setup>
// MvmMobileCatalog.vue — the 暖色 MVM 檔期 view (案 B / #49), the "特價" tab of
// the mobile shell. A pure renderer over the baked 6-檔期 snapshot (lib/mvm.js):
//
//   • OPEN 檔期 chips on a horizontal SLIDER (an 已過期 檔期 is absent — see
//     activePeriods; no 買場/線上 toggle here — this is the 檔期 view).
//   • a section title in the EXACT spec form `N 筆 · 檔期名 · 到 MM/DD · 剩 K 天`
//     (from sectionHeader — count/到期日/剩 K 天 all deciderd in lib/mvm.js).
//   • a round white 篩選 button (funnel line-icon, gate 30a — no emoji).
//   • the ACTIVE 檔期's FULL item list (no fold/trim) of warm product cards.
//
// Colours resolve ONLY through the warm token scope var(--m-*) — no raw hex
// (sloplint gate 48 / the CI css-token guard). Spacing on the shared 4px grid.
// refDate is injectable so a test pins "today" for 剩 K 天 / the 已過期 filter;
// the UI passes none and gets the live clock.
import { ref, computed } from 'vue'
import MobileIcon from './MobileIcon.vue'
import MvmMobileProductCard from './MvmMobileProductCard.vue'
import { periodShort, defaultActiveTab, sectionHeader, activePeriods } from '../../lib/mvm.js'

const props = defineProps({
  tabs: { type: Array, default: () => [] },
  priceTypes: { type: Object, default: () => ({}) },
  initialTab: { type: String, default: '' },
  sourceDate: { type: String, default: '' },
  refDate: { type: Date, default: null },
})

// "today" for the 剩 K 天 / 已過期 math: a test injects a refDate; the UI passes
// none and gets the live clock. Shared by the section header and the 已過期 filter.
const refForHeader = () => (props.refDate instanceof Date ? props.refDate : undefined)

// 切換檔期 renders ONLY periods that are still open. activePeriods drops an
// 已過期 檔期 (its 結束日 < today); empty-but-future 檔期 stay — Kimi only asked
// to remove EXPIRED ones, not empty ones.
const periods = computed(() => activePeriods(props.tabs, refForHeader()))
const hasActive = computed(() => periods.value.length > 0)

// The user's selection (a chip click) / the auto default — first 檔期 with
// products, so the first screen is never an empty grid. NOTE: defaultActiveTab
// scans ALL tabs, so it can name an 已過期 檔期; the resolution below NEVER
// renders a removed chip — it falls back to the first OPEN period the moment a
// selection has expired.
const selectedTab = ref(defaultActiveTab(props.tabs, props.initialTab))
const activeTab = computed(() => {
  const list = periods.value
  if (!list.length) return {} // every 檔期 已結束 -> the graceful empty state
  const sel = list.find((t) => t && t.tab_id === selectedTab.value)
  if (sel) return sel // selection still open -> open it
  const withProducts = list.find((t) => t && Array.isArray(t.products) && t.products.length > 0)
  return withProducts || list[0] || {} // else the first OPEN 檔期 (with products first)
})
const activeTabId = computed(() => activeTab.value.tab_id || '')
const activeTabObj = computed(() => activeTab.value)

// The section title the spec demands: N 筆 · 檔期名 · 到 MM/DD · 剩 K 天.
const header = computed(() => sectionHeader(activeTabObj.value, refForHeader()))

// The active 檔期's FULL item list — no fold/trim — so the whole 檔期 shows.
const products = computed(() =>
  Array.isArray(activeTabObj.value.products) ? activeTabObj.value.products : [],
)
const hasProducts = computed(() => products.value.length > 0)

// The chip's lower line is the full "MM/DD ~ MM/DD" range (Kimi 2026-11-22);
// a date-less 檔期 ("黑色購物週" / "網購星期一") reads "敬請期待", not blank.
// Both go through periodShort (lib/mvm.js) so the display is single-sourced.
const chipRange = (tab) => periodShort(tab)
const isActive = (t) => t && t.tab_id === activeTabId.value

// the 篩選 toggle is a stateless placeholder in this pass (a popover is a later
// build); it flips aria-pressed so the a11y contract + gate 26 stay green.
const filterOpen = ref(false)
function toggleFilter() {
  filterOpen.value = !filterOpen.value
}

function selectTab(t) {
  if (!t || !t.tab_id) return
  selectedTab.value = t.tab_id
  filterOpen.value = false
}
</script>

<template>
  <section class="mvm-m" data-mvm-mobile>
    <template v-if="hasActive">
      <div class="mvm-switch">切換檔期</div>

      <!-- OPEN 檔期 chips on a horizontal SLIDER; an 已過期 檔期 is absent (see
           activePeriods). No 買場/線上 toggle by design. -->
      <nav class="mvm-chips" aria-label="切換檔期">
        <button
          v-for="tab in periods"
          :key="tab.tab_id"
          :data-tab-id="tab.tab_id"
          type="button"
          class="mvm-chip"
          :class="{ 'is-active': isActive(tab), 'is-empty': !(tab && tab.products && tab.products.length) }"
          :aria-pressed="isActive(tab)"
          :aria-label="`檔期 ${tab && tab.label ? tab.label : 'N/A'}，${chipRange(tab)}`"
          @click="selectTab(tab)"
        >
          <span class="mvm-chip-label">{{ tab && tab.label ? tab.label : 'N/A' }}</span>
          <span class="mvm-chip-end">{{ chipRange(tab) }}</span>
        </button>
      </nav>

      <!-- section title in the spec form + the round white 篩選 button -->
      <div class="mvm-section">
        <p class="mvm-title" data-mvm-section-title>{{ header.text }}</p>
        <button
          type="button"
          class="mvm-filter"
          :class="{ 'is-open': filterOpen }"
          :aria-pressed="filterOpen"
          aria-label="篩選"
          data-mvm-filter
          @click="toggleFilter"
        >
          <MobileIcon name="funnel" />
        </button>
      </div>

      <!-- the active 檔期's FULL item list -->
      <main class="mvm-list" :data-active-tab="activeTabId" aria-label="品項目錄">
        <MvmMobileProductCard
          v-for="(product, i) in products"
          :key="`${product && product.sku != null ? product.sku : 'p'}-${i}`"
          :product="product"
          :price-types="priceTypes"
          :tab-price-type="activeTabObj.price_type || ''"
          :end-date="header.range"
        />
        <p v-if="!hasProducts" class="mvm-empty">本檔期尚無可顯示品項</p>
      </main>
    </template>

    <!-- every 檔期 已結束: a graceful empty state — no raw data / no "N/A" -->
    <p v-else class="mvm-empty mvm-empty-all">全部檔期已結束</p>

    <p v-if="sourceDate" class="mvm-foot">圖片欄待補 · 資料於 {{ sourceDate }} 抓取，離線 baked。</p>
  </section>
</template>

<style scoped>
/* Warm token scope var(--m-*) only — no raw hex. Spacing on the shared 4px
 * grid (--sp-*), radius on the shared --radius-*.
 *
 * SCOPED on purpose (review of #49 2026-11-22, must-fix): the chip markup here
 * reuses the class names .mvm-chips / .mvm-chip, which the DARK MvmCatalog.vue
 * filter row also uses. With a global <style> both rule sets are equal-specificity
 * and the LATER (mobile) one won in the minified CSS, restyling the dark PWA's
 * its chips warm-cream + forcing its rows into a single nowrap scroll — a dark-
 * view regression + a fragile source-order dependency. `scoped` appends a
 * data-v-<hash> to every selector so these rules match ONLY this component's
 * nodes and can never leak onto the dark catalog, by any minifier ordering. */
/* Warm token scope var(--m-*) only — no raw hex. Spacing on the shared 4px
 * grid (--sp-*), radius on the shared --radius-*. */
.mvm-m {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  min-width: 0;
}
.mvm-switch {
  font-size: 0.8rem;
  color: var(--m-muted);
}
/* a horizontal SLIDER: 6+ tiles overflow a ~375px phone so it genuinely slides.
 * -webkit-overflow-scrolling is the iOS momentum hint; mandatory snap locks each
 * tile; a thin right-edge fade is the "there is more" cue (keyword colours only,
 * no raw hex, so the CI css-token guard stays clean). No emoji / illustration. */
.mvm-chips {
  display: flex;
  /* NOTE: the dark MvmCatalog.vue also defines a global `.mvm-chips{flex-wrap:wrap}`
   * for its tab bar; since the class name is shared it LEAKS onto the mobile row.
   * Restate nowrap here (later rule, equal specificity) to force the single-row
   * horizontal slider the design wants — a 5-tile row overflows a ~375 phone. */
  flex-wrap: nowrap;
  gap: var(--sp-2);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scroll-snap-type: x mandatory;
  padding-bottom: var(--sp-2);
  -webkit-mask-image: linear-gradient(90deg, black 0, black calc(100% - 16px), transparent 100%);
  mask-image: linear-gradient(90deg, black 0, black calc(100% - 16px), transparent 100%);
}
.mvm-chip {
  /* a rounded-SQUARE tile on the slider (a control, not a card). Column layout so
   * the name sits ABOVE its date line. 64px tile floor (the 44px gate-39b floor
   * sits on the global min-height in style.css; restated here so it reads as a
   * square, not a thin pill); 104px wide so 6 tiles overflow a ~375px phone. */
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: var(--sp-1);
  flex: 0 0 auto;
  min-width: 104px;
  min-height: 64px;
  padding: var(--sp-2) var(--sp-3);
  background: var(--m-chip-bg);
  color: var(--m-chip-ink);
  border: 1px solid var(--m-hairline);
  border-radius: var(--radius-lg);
  cursor: pointer;
  white-space: nowrap;
  font-family: var(--font-sans);
  scroll-snap-align: start;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.mvm-chip-label {
  /* line 1: the 檔期 name (bold) */
  font-weight: 600;
  font-size: 0.88rem;
  line-height: 1.2;
}
.mvm-chip-end {
  /* line 2: the "到 MM/DD" date (smaller + muted); absent for a no-date 檔期 */
  font-size: 0.72rem;
  color: var(--m-muted);
  line-height: 1.2;
}
.mvm-chip:hover {
  border-color: var(--m-brand);
}
.mvm-chip.is-empty {
  opacity: 0.6;
}
.mvm-chip.is-active {
  background: var(--m-brand);
  border-color: var(--m-brand);
  color: var(--m-brand-ink);
}
.mvm-chip.is-active .mvm-chip-end {
  color: var(--m-brand-ink);
  opacity: 0.85;
}
.mvm-chip:active {
  transform: scale(0.98);
}
.mvm-chip:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}
.mvm-chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* section title + round white filter button */
.mvm-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}
.mvm-title {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--m-ink-2);
  font-variant-numeric: tabular-nums;
}
.mvm-filter {
  /* the round white 篩選 button (funnel line-icon, no emoji — gate 30a). */
  flex: 0 0 auto;
  width: 44px;
  height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--m-card);
  color: var(--m-ink-2);
  border: 1px solid var(--m-hairline);
  border-radius: var(--radius-pill);
  cursor: pointer;
  padding: 0;
  box-shadow: 0 1px 2px var(--m-shadow);
  transition: background 0.15s, border-color 0.15s;
}
.mvm-filter.is-open {
  color: var(--m-brand);
  border-color: var(--m-brand);
}
.mvm-filter:active {
  transform: scale(0.96);
}
.mvm-filter:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}
.mvm-filter:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* the FULL active-檔期 list — one warm card per item, no fold */
.mvm-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.mvm-empty {
  color: var(--m-muted);
  font-size: 0.85rem;
  padding: var(--sp-4);
  text-align: center;
}
.mvm-foot {
  margin: var(--sp-4) 0 0;
  color: var(--m-muted);
  font-size: 0.72rem;
  border-top: 1px solid var(--m-hairline);
  padding-top: var(--sp-3);
}
</style>
