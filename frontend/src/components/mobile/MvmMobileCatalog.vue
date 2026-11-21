<script setup>
// MvmMobileCatalog.vue — the 暖色 MVM 檔期 view (案 B / #49), the "特價" tab of
// the mobile shell. A pure renderer over the baked 6-檔期 snapshot (lib/mvm.js):
//
//   • 6 檔期 chips on a horizontal scroll axis (no 買場/線上 toggle here — this is
//     the 檔期 view, per the 檔期 mockup).
//   • a section title in the EXACT spec form `N 筆 · 檔期名 · 到 MM/DD · 剩 K 天`
//     (from sectionHeader — count/到期日/剩 K 天 all deciderd in lib/mvm.js).
//   • a round white 篩選 button (funnel line-icon, gate 30a — no emoji).
//   • the ACTIVE 檔期's FULL item list (no fold/trim) of warm product cards.
//
// Colours resolve ONLY through the warm token scope var(--m-*) — no raw hex
// (sloplint gate 48 / the CI css-token guard). Spacing on the shared 4px grid.
// refDate is injectable so a test pins "today" for 剩 K 天; the UI passes none.
import { ref, computed } from 'vue'
import MobileIcon from './MobileIcon.vue'
import MvmMobileProductCard from './MvmMobileProductCard.vue'
import { defaultActiveTab, sectionHeader } from '../../lib/mvm.js'

const props = defineProps({
  tabs: { type: Array, default: () => [] },
  priceTypes: { type: Object, default: () => ({}) },
  initialTab: { type: String, default: '' },
  sourceDate: { type: String, default: '' },
  refDate: { type: Date, default: null },
})

// The active 檔期. defaultActiveTab opens the first 檔期 that carries products,
// so the first screen is never an empty grid (an empty 檔期 still opens on click).
const activeTab = ref(defaultActiveTab(props.tabs, props.initialTab))
const activeTabObj = computed(
  () => props.tabs.find((t) => t && t.tab_id === activeTab.value) || props.tabs[0] || {},
)

// The section title the spec demands: N 筆 · 檔期名 · 到 MM/DD · 剩 K 天.
const refForHeader = () => (props.refDate instanceof Date ? props.refDate : undefined)
const header = computed(() => sectionHeader(activeTabObj.value, refForHeader()))

// The active 檔期's FULL item list — no fold/trim — so the whole 檔期 shows.
const products = computed(() =>
  Array.isArray(activeTabObj.value.products) ? activeTabObj.value.products : [],
)
const hasProducts = computed(() => products.value.length > 0)

// A compact "到 MM/DD" tail per chip; a date-less 檔期 ("敬請期待") shows none.
const chipEnd = (tab) => {
  const h = sectionHeader(tab, refForHeader())
  return h.end && h.end !== 'N/A' ? `· 到 ${h.end}` : ''
}
const isActive = (t) => t && t.tab_id === activeTab.value

// the 篩選 toggle is a stateless placeholder in this pass (a popover is a later
// build); it flips aria-pressed so the a11y contract + gate 26 stay green.
const filterOpen = ref(false)
function toggleFilter() {
  filterOpen.value = !filterOpen.value
}

function selectTab(t) {
  if (!t || !t.tab_id) return
  activeTab.value = t.tab_id
  filterOpen.value = false
}
</script>

<template>
  <section class="mvm-m" data-mvm-mobile>
    <div class="mvm-switch">切換檔期</div>

    <!-- 6 檔期 chips, horizontal scroll axis. No 買場/線上 toggle by design. -->
    <nav class="mvm-chips" aria-label="切換檔期">
      <button
        v-for="tab in tabs"
        :key="tab.tab_id"
        type="button"
        class="mvm-chip"
        :class="{ 'is-active': isActive(tab), 'is-empty': !(tab && tab.products && tab.products.length) }"
        :aria-pressed="isActive(tab)"
        :aria-label="`檔期 ${tab && tab.label ? tab.label : 'N/A'}${tab && tab.period ? '，' + tab.period : ''}`"
        @click="selectTab(tab)"
      >
        <span class="mvm-chip-label">{{ tab && tab.label ? tab.label : 'N/A' }}</span>
        <span v-if="chipEnd(tab)" class="mvm-chip-end">{{ chipEnd(tab) }}</span>
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
    <main class="mvm-list" :data-active-tab="activeTab" aria-label="品項目錄">
      <MvmMobileProductCard
        v-for="(product, i) in products"
        :key="`${product && product.sku != null ? product.sku : 'p'}-${i}`"
        :product="product"
        :price-types="priceTypes"
        :tab-price-type="activeTabObj.price_type || ''"
        :end-date="header.end"
      />
      <p v-if="!hasProducts" class="mvm-empty">本檔期尚無可顯示品項</p>
    </main>

    <p v-if="sourceDate" class="mvm-foot">圖片欄待補 · 資料於 {{ sourceDate }} 抓取，離線 baked。</p>
  </section>
</template>

<style>
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
/* horizontal scroll axis: no wrapping, no vertical stack. */
.mvm-chips {
  display: flex;
  gap: var(--sp-2);
  overflow-x: auto;
  scroll-snap-type: x proximity;
  padding-bottom: var(--sp-1);
}
.mvm-chip {
  /* a control, not a card (gate 4). 44px hit floor (gate 39b is satisfied by the
   * global min-height in style.css; restated here for the chip). */
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  min-height: 44px;
  padding: var(--sp-2) var(--sp-3);
  background: var(--m-chip-bg);
  color: var(--m-chip-ink);
  border: 1px solid var(--m-hairline);
  border-radius: var(--radius-pill);
  cursor: pointer;
  white-space: nowrap;
  font-family: var(--font-sans);
  flex: 0 0 auto;
  scroll-snap-align: start;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.mvm-chip-label {
  font-weight: 600;
  font-size: 0.9rem;
}
.mvm-chip-end {
  font-size: 0.75rem;
  color: var(--m-muted);
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
