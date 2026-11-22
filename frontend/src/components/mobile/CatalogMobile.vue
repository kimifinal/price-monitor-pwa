<script setup>
// CatalogMobile.vue — the 全部商品 全庫 view (#50), the "全部" tab of the mobile
// shell. A pure renderer over the baked 10,049-item catalog (lib/catalog.js):
//
//   • a 買場/線上 sliding TOGGLE (the ONE place the app hides the 4,693 網路獨家
//     items — 'store' mode drops them, 'online' shows the whole 全庫).
//   • a count bar under the toggle (`countBarText`: store → "5,356 筆買場可購 ·
//     4,693 項線上 專 屬已隱藏"; online → "10,049 筆全庫 · 含 4,693 項線上 專 屬").
//   • a round white 篩選 button (funnel line-icon, gate 30a — no emoji), same as
//     MvmMobileCatalog (a popover is a later build; it flips aria-pressed so the
//     a11y contract + gate 26 stay green).
//   • a paginated item list of warm cards: first 50, "顯示更多" loads 50 more.
//     No 檔期 chips — this is the 全庫, not a 檔期.
//
// Colours resolve ONLY through the warm token scope var(--m-*) — no raw hex
// (sloplint gate 48 / the CI css-token guard). Spacing on the shared 4px grid.
// Everything the view shows (the counts, the price line, the 折) is decided in
// lib/catalog.js so the template re-derives no number.
import { ref, computed } from 'vue'
import MobileIcon from './MobileIcon.vue'
import CatalogProductCard from './CatalogProductCard.vue'
import {
  filterByMode,
  catalogStats,
  countBarText,
  paginate,
  hasMore,
} from '../../lib/catalog.js'
import { formatTWD } from '../../lib/format.js'

const props = defineProps({
  // the baked 全庫 (loadCatalog()'s output), an array of catalog items
  catalog: { type: Array, default: () => [] },
  // items per "顯示更多" page; 50 in production, overridable so a test can
  // exercise pagination with a tiny fixture
  pageSize: { type: Number, default: 50 },
})

const emit = defineEmits(['modechange', 'pagechange', 'filtertoggle'])

// The 買場/線上 toggle state. 'store' (default) hides the 網路獨家 items; 'online'
// shows the whole 全庫.
const mode = ref('store')
// the current pagination page (0-indexed); "顯示更多" advances it.
const page = ref(0)
// the 篩選 toggle is a stateless placeholder in this pass.
const filterOpen = ref(false)

// The whole 全庫's three counts (total / store / onlineOnly), single-sourced.
const stats = computed(() => catalogStats(props.catalog))
const totalCount = computed(() => stats.value.total)
const storeCount = computed(() => stats.value.store)

// The active mode's filtered list: 'store' drops the 網路獨家 items.
const filteredProducts = computed(() => filterByMode(props.catalog, mode.value))
const hasProducts = computed(() => filteredProducts.value.length > 0)

// The "顯示更多" accumulation: show the first (page+1)*pageSize items, so each
// click reveals 50 MORE (the list grows rather than swapping a fixed window).
const visibleProducts = computed(() =>
  paginate(filteredProducts.value, 0, (page.value + 1) * props.pageSize),
)
const hasMoreProducts = computed(() => hasMore(filteredProducts.value, page.value, props.pageSize))

// The count-bar text the spec demands, for the active mode.
const countText = computed(() => countBarText(props.catalog, mode.value))

function selectMode(next) {
  const m = next === 'online' ? 'online' : 'store'
  if (mode.value === m) return
  mode.value = m
  page.value = 0 // switching mode restarts pagination from the top
  emit('modechange', m)
}

function loadMore() {
  page.value += 1
  emit('pagechange', page.value)
}

function toggleFilter() {
  filterOpen.value = !filterOpen.value
  emit('filtertoggle', filterOpen.value)
}
</script>

<template>
  <section class="cat-m" data-cat-mobile>
    <!-- 買場/線上 sliding toggle: the ONE place the 網路獨家 items hide. The
         active segment is 品牌紅; the inactive is warm-white. Each segment shows
         its set's count (買場 → 5,356 store, 線上 → 10,049 total). -->
    <div class="cat-toggle" data-buyonline-toggle role="group" aria-label="買場/線上切換">
      <button
        type="button"
        class="cat-seg"
        :class="{ 'is-active': mode === 'store' }"
        :aria-pressed="mode === 'store'"
        data-seg="store"
        @click="selectMode('store')"
      >
        買場<span class="cat-count">{{ formatTWD(storeCount) }}</span>
      </button>
      <button
        type="button"
        class="cat-seg"
        :class="{ 'is-active': mode === 'online' }"
        :aria-pressed="mode === 'online'"
        data-seg="online"
        @click="selectMode('online')"
      >
        線上<span class="cat-count">{{ formatTWD(totalCount) }}</span>
      </button>
    </div>

    <!-- count bar + the round white 篩選 button -->
    <div class="cat-section">
      <p class="cat-count-bar" data-cat-count>{{ countText }}</p>
      <button
        type="button"
        class="cat-filter"
        :class="{ 'is-open': filterOpen }"
        :aria-pressed="filterOpen"
        aria-label="篩選"
        data-cat-filter
        @click="toggleFilter"
      >
        <MobileIcon name="funnel" />
      </button>
    </div>

    <!-- the active mode's paginated item list -->
    <main class="cat-list" :data-mode="mode" aria-label="全部商品目錄">
      <CatalogProductCard
        v-for="(product, i) in visibleProducts"
        :key="`${product && product.sku != null ? product.sku : 'p'}-${i}`"
        :product="product"
        :mode="mode"
      />
      <p v-if="!hasProducts" class="cat-empty">本模式尚無可顯示品項</p>
      <button
        v-if="hasMoreProducts"
        type="button"
        class="cat-more"
        data-cat-more
        @click="loadMore"
      >
        顯示更多
      </button>
    </main>
  </section>
</template>

<style scoped>
/* Warm token scope var(--m-*) only — no raw hex. Spacing on the shared 4px
 * grid (--sp-*), radius on the shared --radius-*. SCOPED so these never leak
 * onto the dark catalog (see MvmMobileCatalog.vue's note on the shared class
 * names). */
.cat-m {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  min-width: 0;
}

/* 買場/線上 sliding toggle — a two-segment control on a warm-gray track. The
 * active segment slides to 品牌紅; the inactive stays warm-white. */
.cat-toggle {
  display: flex;
  gap: var(--sp-1);
  padding: var(--sp-1);
  background: var(--m-toggle-bg);
  border-radius: var(--radius-pill);
}
.cat-seg {
  flex: 1 1 0;
  min-height: 44px; /* gate 39b: a 44px touch target */
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-1);
  padding: var(--sp-2) var(--sp-3);
  border: none;
  border-radius: var(--radius-pill);
  background: var(--m-card);
  color: var(--m-ink-2);
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.cat-seg .cat-count {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 0.78rem;
  opacity: 0.85;
}
.cat-seg.is-active {
  background: var(--m-toggle-active);
  color: var(--m-brand-ink);
}
.cat-seg.is-active .cat-count {
  opacity: 1;
}
.cat-seg:active {
  transform: scale(0.98);
}
.cat-seg:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}

/* count bar + round white 篩選 button */
.cat-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}
.cat-count-bar {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--m-ink-2);
  font-variant-numeric: tabular-nums;
}
.cat-filter {
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
.cat-filter.is-open {
  color: var(--m-brand);
  border-color: var(--m-brand);
}
.cat-filter:active {
  transform: scale(0.96);
}
.cat-filter:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}

/* the paginated 全庫 list — one warm card per item */
.cat-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.cat-empty {
  color: var(--m-muted);
  font-size: 0.85rem;
  padding: var(--sp-4);
  text-align: center;
}
.cat-more {
  align-self: center;
  min-height: 44px;
  padding: var(--sp-2) var(--sp-4);
  border: 1px solid var(--m-hairline);
  border-radius: var(--radius-pill);
  background: var(--m-card);
  color: var(--m-ink-2);
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 0.85rem;
  cursor: pointer;
  box-shadow: 0 1px 2px var(--m-shadow);
  transition: background 0.15s, color 0.15s;
}
.cat-more:hover {
  color: var(--m-brand);
  border-color: var(--m-brand);
}
.cat-more:active {
  transform: scale(0.98);
}
.cat-more:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}
</style>
