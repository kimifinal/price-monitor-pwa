<script setup>
// MvmCatalog.vue — the MVM 檔期目錄 page. A pure renderer over the OFFLINE-BAKED
// snapshot (lib/mvm.js, no network): a 6-檔期 tab bar, a type legend, the active
// tab's products in a 1->2 column grid, plus a discount/category/price sort and a
// category filter. Q2 = LAZY: only the ACTIVE tab's grid renders (a button that
// isn't active mounts no cards). Colours resolve through the design-token SSOT
// (style.css) — no raw hex (CI CSS-token guard + sloplint gate 48); spacing on the
// 4px token grid (--sp-*, gate 24a/24b); headings carry SectionIcon line-icons
// (sloplint gate 30a, no emoji); the "查看" link is a pure verb (gate 63, no glued arrow).
import { ref, computed } from 'vue'
import SectionIcon from './SectionIcon.vue'
import MvmProductCard from './MvmProductCard.vue'
import {
  defaultActiveTab,
  tabCountText,
  categoriesOf,
  filterByCategory,
  sortProducts,
} from '../lib/mvm.js'

const props = defineProps({
  // costco_mvm.tabs (6 檔期)
  tabs: { type: Array, default: () => [] },
  // costco_mvm.price_types (3 types + label/meaning)
  priceTypes: { type: Object, default: () => ({}) },
  // the tab to open first (else the first tab that carries products)
  initialTab: { type: String, default: '' },
  // the crawl date, shown in the footer (else the footer omits it)
  sourceDate: { type: String, default: '' },
})

// active 檔期 — a button that isn't this stays un-rendered (lazy grid, Q2).
const activeTab = ref(defaultActiveTab(props.tabs, props.initialTab))

const activeTabObj = computed(
  () => props.tabs.find((t) => t && t.tab_id === activeTab.value) || props.tabs[0] || {},
)

// --- sort + filter (Q3/Q4). Default = 折幅 desc, the most useful ordering. ---
const sortMode = ref('discount') // 'discount' | 'category' | 'price'
const catFilter = ref('all')

// categories present in the ACTIVE tab only — the filter chips stay in view.
const categories = computed(() => categoriesOf(activeTabObj.value.products))
const cats = computed(() => ['all', ...categories.value])

// the cards the active tab actually shows: filtered by category, then sorted.
const visible = computed(() =>
  sortProducts(filterByCategory(activeTabObj.value.products || [], catFilter.value), sortMode.value),
)

const hasActiveProducts = computed(() => (activeTabObj.value.products || []).length > 0)

// --- legend: one row per price_type (the catalog's 3 badge types) ---
const legend = computed(() =>
  Object.entries(props.priceTypes || {}).map(([key, meta]) => ({
    key,
    label: (meta && meta.label) || key,
    meaning: (meta && meta.meaning) || '',
  })),
)

// --- tab helpers (pure, from lib/mvm.js) ---
const isActive = (t) => t.tab_id === activeTab.value
const isEmpty = (t) => (t.products || []).length === 0

// switching tabs / filter resets to the active tab's own products.
function selectTab(t) {
  if (!t || !t.tab_id) return
  activeTab.value = t.tab_id
  catFilter.value = 'all'
}
function selectCat(c) {
  catFilter.value = c
}
function selectSort(m) {
  sortMode.value = m
}

const SORT_MODES = [
  { key: 'discount', label: '折幅' },
  { key: 'category', label: '類別' },
  { key: 'price', label: '金額' },
]

const footerText = computed(() =>
  props.sourceDate ? `圖片欄待補。資料於 ${props.sourceDate} 抓取，離線 baked。` : '圖片欄待補。',
)
</script>

<template>
  <section class="mvm-catalog" data-mvm-catalog>
    <header class="mvm-hd">
      <h1 class="mvm-title">
        <SectionIcon name="tag" title="MVM 檔期目錄圖示" />
        <span>好市多 MVM 檔期</span>
      </h1>
      <p class="mvm-sub">
        每週檔期目錄，離線 baked：選一檔期，看該期間所有品項的品名、促價、折幅、類型與分類。
      </p>
    </header>

    <!-- 6 檔期 tab bar. Each is a real <button>; the non-active ones mount no grid. -->
    <nav class="mvm-tabs" aria-label="選擇檔期">
      <button
        v-for="tab in tabs"
        :key="tab.tab_id"
        type="button"
        class="mvm-tab"
        :class="{ 'is-active': isActive(tab), 'is-empty': isEmpty(tab) }"
        :aria-pressed="isActive(tab)"
        :aria-label="`檔期 ${tab.label || 'N/A'}${tab.period ? '，' + tab.period : ''}`"
        @click="selectTab(tab)"
      >
        <span class="tab-label">{{ tab.label || 'N/A' }}</span>
        <span class="tab-period">{{ tab.period || 'N/A' }}</span>
        <span class="tab-count">{{ tabCountText(tab) }} 筆</span>
      </button>
    </nav>

    <!-- type legend: one row per price_type from the baked price_types map -->
    <div class="mvm-legend" aria-label="類型圖例">
      <p v-for="row in legend" :key="row.key" class="mvm-legend-row">
        <span class="badge" :class="`badge-${row.key}`">{{ row.label }}</span>
        <span v-if="row.meaning" class="mvm-legend-meaning">{{ row.meaning }}</span>
      </p>
    </div>

    <!-- sort + category filter (Q3/Q4). Chip labels are sentence-case, body face. -->
    <div class="mvm-controls" role="group" aria-label="排序與篩選">
      <div class="mvm-chips" role="group" aria-label="排序方式">
        <button
          v-for="m in SORT_MODES"
          :key="m.key"
          type="button"
          class="mvm-chip"
          :class="{ 'is-active': sortMode === m.key }"
          :aria-pressed="sortMode === m.key"
          @click="selectSort(m.key)"
        >
          {{ m.label }}
        </button>
      </div>
      <div v-if="cats.length > 1" class="mvm-chips" role="group" aria-label="類別篩選">
        <button
          v-for="c in cats"
          :key="c"
          type="button"
          class="mvm-chip"
          :class="{ 'is-active': catFilter === c }"
          :aria-pressed="catFilter === c"
          @click="selectCat(c)"
        >
          {{ c === 'all' ? '全部' : c }}
        </button>
      </div>
    </div>

    <!-- the active tab's grid (lazy: only one tab's cards mount at a time, Q2). -->
    <main class="mvm-grid" :data-active-tab="activeTab" aria-label="品項目錄">
      <MvmProductCard
        v-for="(product, i) in visible"
        :key="`${product?.sku ?? 'p'}-${i}`"
        :product="product"
        :price-types="priceTypes"
      />
      <p v-if="!hasActiveProducts" class="mvm-empty">本檔期尚無可顯示品項。</p>
      <p
        v-else-if="!visible.length"
        class="mvm-empty"
        >此類別尚未有品項，請換一類或清除篩選。</p
      >
    </main>

    <footer class="mvm-foot">{{ footerText }}</footer>
  </section>
</template>

<style>
/* Colours ONLY as var(--token) — CI guards raw 6-digit hex in .vue and sloplint
 * gate 48 blocks a colour literal outside the token block. Spacing on the 4px
 * token grid (--sp-*, no 1/2/6 px values: gate 24b). */
.mvm-catalog {
  color: var(--text);
  max-width: 100%;
}
.mvm-hd {
  margin-bottom: var(--sp-5);
}
.mvm-title {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: 1.4rem;
  font-weight: 600;
  color: var(--text);
  margin: 0;
  line-height: 1.25;
}
.mvm-title svg {
  color: var(--accent-hover);
  flex: 0 0 auto;
}
.mvm-sub {
  color: var(--text-3);
  font-size: 0.85rem;
  line-height: 1.5;
  margin: var(--sp-2) 0 0;
  max-width: 60ch;
}

/* tab bar */
.mvm-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin: var(--sp-4) 0;
}
.mvm-tab {
  /* a control, not a card (gate 4: no card-in-card). min 44x44 hit area (gate 39b). */
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
  min-height: 44px;
  min-width: 120px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--sp-3);
  text-align: left;
  color: var(--text-2);
  cursor: pointer;
  font-family: inherit;
}
.mvm-tab:hover {
  border-color: var(--border-2);
}
.mvm-tab.is-active {
  border-color: var(--accent);
  background: var(--surface-1);
  color: var(--text);
}
.mvm-tab.is-empty {
  opacity: 0.5;
}
.tab-label {
  font-weight: 600;
  color: var(--text);
  font-size: 0.95rem;
  white-space: nowrap;
}
.tab-period,
.tab-count {
  font-variant-numeric: tabular-nums;
  font-family: var(--font-mono);
  font-size: 0.75rem;
}
.tab-period {
  color: var(--text-3);
}
.tab-count {
  color: var(--text-2);
}

/* legend */
.mvm-legend {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  margin: 0 0 var(--sp-4);
  padding: var(--sp-3);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.mvm-legend-row {
  display: flex;
  gap: var(--sp-2);
  align-items: baseline;
  flex-wrap: wrap;
  font-size: 0.82rem;
  color: var(--text-2);
  margin: 0;
}
.mvm-legend-meaning {
  color: var(--text-3);
}

/* type badges (re-used from MvmProductCard's badge colours) */
.badge {
  /* gate 64: body face, one step smaller, normal case. NOT mono costume.
   * letter-spacing 0.02em (gate 67 ceiling is 0.03em). */
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 0.72rem;
  padding: var(--sp-1) 8px;
  border-radius: var(--radius-pill);
  border: 1px solid currentColor;
  line-height: 1.6;
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.badge-online_only { color: var(--link); }
.badge-store_online_diff { color: var(--good-deal); }
.badge-store_only { color: var(--sku); }

/* sort + filter chips (Q3/Q4). A control in the body face, sentence case (gate 67). */
.mvm-controls {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  margin-bottom: var(--sp-4);
}
.mvm-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
}
.mvm-chip {
  font-family: var(--font-sans);
  font-size: 0.82rem;
  line-height: 1.2;
  color: var(--text-2);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  padding: var(--sp-2) var(--sp-3);
  min-height: 44px;
  cursor: pointer;
  white-space: nowrap;
}
.mvm-chip:hover {
  border-color: var(--border-2);
}
.mvm-chip.is-active {
  border-color: var(--accent);
  background: var(--surface-1);
  color: var(--text);
}

/* product grid: 1 column on mobile, 2 at >= 720px. Tracks use 1fr (no image track,
 * so gate 50's minmax(0,1fr)/img-track rule does not bite — the images live in
 * the card's fixed 88px slot). */
.mvm-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--sp-3);
  margin-top: var(--sp-4);
}
@media (min-width: 720px) {
  .mvm-grid {
    grid-template-columns: 1fr 1fr;
  }
}
.mvm-empty {
  color: var(--text-3);
  font-size: 0.85rem;
  padding: var(--sp-3);
  grid-column: 1 / -1;
}

.mvm-foot {
  margin-top: var(--sp-8);
  color: var(--muted);
  font-size: 0.72rem;
  border-top: 1px solid var(--border);
  padding-top: var(--sp-3);
}

/* gate 26a/26b: full interactive states on every control, token-driven. focus is
 * instant (gate 15 — no fade) at 3:1+ on --accent-hover vs the dark surfaces. */
.mvm-tab:focus-visible,
.mvm-chip:focus-visible {
  outline: 2px solid var(--accent-hover);
  outline-offset: 2px;
}
.mvm-tab:active,
.mvm-chip:active {
  filter: brightness(1.12);
}
.mvm-tab:disabled,
.mvm-chip:disabled,
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
