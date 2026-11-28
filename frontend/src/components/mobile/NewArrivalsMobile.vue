<template>
  <section class="na" aria-label="新品分頁">
    <!-- Period chips: 近 7 天 / 近 14 天 / 近 30 天 / 全部 — 30 default, REAL filter
         (switching recomputes the list) -->
    <div class="na-periods" role="group" aria-label="上線時段">
      <button
        v-for="p in PERIODS"
        :key="p.value"
        type="button"
        class="na-period"
        :class="{ 'is-active': period === p.value }"
        :aria-pressed="period === p.value"
        @click="onPeriod(p.value)"
      >
        {{ p.label }}
      </button>
    </div>

    <!-- Category chips: REAL filter, derived from the costco-history `tag` field. -->
    <div class="na-cats" role="group" aria-label="類別篩選">
      <button
        v-for="c in catList"
        :key="c"
        type="button"
        class="na-cat-chip"
        :class="{ 'is-active': activeCat === c }"
        :aria-pressed="activeCat === c"
        @click="onCat(c)"
      >
        {{ c }}
      </button>
    </div>

    <!-- Section head: "N 筆 · 新品 · 近 K 天" + a stateless 篩選/漏斗 placeholder. -->
    <div class="na-head">
      <h2 class="na-title">{{ sectionTitle }}</h2>
      <button
        type="button"
        class="na-funnel"
        aria-label="篩選"
        :aria-expanded="isFunnelOpen"
        @click="onFunnel"
      >
        <MobileIcon name="funnel" :size="18" />
        <span>篩選</span>
      </button>
    </div>

    <!-- Card list (NewArrivalCard, NOT MvmMobileProductCard). -->
    <div v-if="list.length" class="na-list">
      <NewArrivalCard
        v-for="item in list"
        :key="item.sku"
        :item="item"
        :ref-date="now"
      />
    </div>
    <p v-else class="na-empty">這個時段沒有新品</p>

    <p class="na-note">
      探索導向：依上線時間排序，省錢僅作副標籤。不展示約 X 折、不做通路對比。
    </p>
  </section>
</template>

<script setup>
import { ref, computed } from 'vue'
import MobileIcon from './MobileIcon.vue'
import NewArrivalCard from './NewArrivalCard.vue'
import {
  newArrivals,
  withinPeriods,
  categories as deriveCategories,
} from '../../lib/newarrivals.js'

const PERIODS = [
  { value: 7, label: '近 7 天' },
  { value: 14, label: '近 14 天' },
  { value: 30, label: '近 30 天' },
  { value: 'all', label: '全部' },
]

const props = defineProps({
  // Injectable ref date so tests stay deterministic; defaults to "now" in prod.
  refDate: { type: [Date, null], default: null },
})

const now = computed(() =>
  props.refDate instanceof Date ? props.refDate : new Date(),
)

const period = ref(30) // 30 is the default window.
const activeCat = ref('全部')
const isFunnelOpen = ref(false)

// Full catalog (every item, newest first) drives the category chips so they
// stay STABLE when the period changes — categories come from the data, not the
// current slice.
const allItems = computed(() =>
  newArrivals(Number.POSITIVE_INFINITY, now.value),
)
const catList = computed(() => ['全部', ...deriveCategories(allItems.value)])

// The list = period filter ∩ category filter, newest first.
const list = computed(() => {
  let items = withinPeriods(allItems.value, period.value, now.value)
  if (activeCat.value !== '全部') {
    items = items.filter((i) => i && i.tag === activeCat.value)
  }
  return items
})

const count = computed(() => list.value.length)
const periodLabel = computed(() =>
  period.value === 'all' ? '全部' : `近 ${period.value} 天`,
)
const sectionTitle = computed(() => `${count.value} 筆 · 新品 · ${periodLabel.value}`)

function onPeriod(value) {
  period.value = value
}
function onCat(c) {
  activeCat.value = c
}
function onFunnel() {
  // Stateless placeholder — mirrors MvmMobileCatalog's funnel toggle (no panel yet).
  isFunnelOpen.value = !isFunnelOpen.value
}

defineExpose({
  list,
  catList,
  count,
  period,
  activeCat,
  sectionTitle,
})
</script>

<style scoped>
/* Warm token scope var(--m-*) only — no raw hex (CI css-token guard / sloplint
   gate 48). Spacing on the shared 4px grid (--sp-*), radius on --radius-*, fonts
   on --font-*. Scoped so these rules match only this component's nodes and never
   bleed onto the dark catalog. No emoji (gate 30a). */
.na {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  min-width: 0;
  padding: var(--sp-3) var(--sp-4) calc(var(--sp-6) + env(safe-area-inset-bottom, 0px));
}

.na-periods,
.na-cats {
  display: flex;
  flex-wrap: nowrap;
  gap: var(--sp-2);
  overflow-x: auto;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
}
.na-periods::-webkit-scrollbar,
.na-cats::-webkit-scrollbar {
  display: none;
}

.na-period,
.na-cat-chip {
  flex: 0 0 auto;
  min-height: 44px;
  padding: 8px 14px;
  font-family: var(--font-sans);
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--m-ink-2);
  background: var(--m-card);
  border: 1px solid var(--m-hairline);
  border-radius: var(--radius-pill);
  cursor: pointer;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  touch-action: manipulation;
  transition: background 120ms ease, color 120ms ease, border-color 120ms ease;
}
.na-period:hover,
.na-cat-chip:hover {
  background: var(--m-soft);
}
.na-period.is-active {
  background: var(--m-brand);
  color: var(--m-brand-ink);
  border-color: var(--m-brand);
}
.na-cat-chip.is-active {
  background: var(--m-ink);
  color: var(--m-card);
  border-color: var(--m-ink);
}
.na-cat-chip:focus-visible,
.na-period:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}

.na-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}
.na-title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--m-ink);
  display: inline-flex;
  align-items: baseline;
  gap: var(--sp-2);
}
.na-funnel {
  flex: 0 0 auto;
  width: 44px;
  height: 44px;
  min-width: 44px;
  min-height: 44px;
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
  touch-action: manipulation;
  transition: background 120ms ease, color 120ms ease;
}
.na-funnel.is-open,
.na-funnel[aria-expanded='true'] {
  color: var(--m-brand);
  border-color: var(--m-brand);
}
.na-funnel:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}
.na-funnel svg {
  width: 20px;
  height: 20px;
}

.na-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.na-empty {
  margin: 0;
  padding: var(--sp-8) var(--sp-4);
  text-align: center;
  font-size: 0.85rem;
  color: var(--m-muted);
}
.na-note {
  margin: 0;
  font-size: 0.72rem;
  line-height: 1.5;
  color: var(--m-muted);
  border-top: 1px solid var(--m-hairline);
  padding-top: var(--sp-3);
}

@media (prefers-reduced-motion: reduce) {
  .na-period,
  .na-cat-chip,
  .na-funnel {
    transition: none;
  }
}
</style>
