<script setup>
// PriceHistory.vue — renders one product's price-history card: an SVG
// sparkline + a verdict badge ("歷史最低 / 接近高點 / ..."). It is a PURE
// renderer: it never re-derives the verdict — it imports priceVerdict +
// sparkPath from the single source of truth (monitor.js).
//
// The card is source-agnostic: a Costco item flows through the SAME priceVerdict,
// with a small source badge (🛒 costco). No per-source verdict logic.
import { computed } from 'vue'
import { priceVerdict, sparkPath } from '../lib/monitor.js'

const props = defineProps({
  // card: { name, current, source?, tag?, currency?,
  //         series: [{observed_at, price}],
  //         metrics: {points, atAllTimeLow, dropPctFromHigh} }
  card: { type: Object, required: true },
})

const verdict = computed(() => priceVerdict(props.card?.metrics))
const path = computed(() => sparkPath(props.card?.series || [], 240, 34, 2))

// The sparkline colour tracks the verdict so a good deal visually pops.
// Colours resolve through the token SSOT (style.css): same hexes, by reference,
// so a hand-tuned token stays in one place. Structure/keys/fallback unchanged.
const stroke = computed(() =>
  ({
    all_time_low: 'var(--success)',
    good_deal: 'var(--good-deal)',
    stable: 'var(--text-2)',
    near_high: 'var(--warn)',
    unknown: 'var(--muted)',
  })[verdict.value.verdict] || 'var(--text-2)',
)

const points = computed(() => props.card?.series?.length || props.card?.metrics?.points || 0)

// Source badge: a Costco item wears a 🛒. The verdict stays the single SSOT.
const source = computed(() => props.card?.source || props.card?.tag || 'costco')
const kindIcon = computed(() => '🛒')
const sourceLabel = computed(() => source.value)
const currency = computed(() => props.card?.currency || '')
const srcText = computed(() =>
  `${kindIcon.value} ${sourceLabel.value}${currency.value ? ` · ${currency.value}` : ''}`,
)
</script>

<template>
  <div class="price-history" :data-verdict="verdict.verdict" :data-source="source">
    <div class="ph-head">
      <strong class="ph-name">{{ card.name || '未命名' }}</strong>
      <div class="ph-tags">
        <span class="ph-src">{{ srcText }}</span>
        <span class="ph-badge" :style="{ color: stroke }">📊 {{ verdict.label }}</span>
      </div>
    </div>
    <div class="ph-spark">
      <svg :viewBox="`0 0 240 34`" width="100%" height="34" preserveAspectRatio="none"
           v-if="path" aria-label="價格走勢">
        <path :d="path" :stroke="stroke" fill="none" stroke-width="1.5"
              stroke-linejoin="round" stroke-linecap="round" />
      </svg>
      <span v-else class="ph-no">尚無歷史</span>
    </div>
    <div class="ph-foot">
      <span class="ph-now">${{ Number(card.current || 0).toLocaleString() }}</span>
      <span class="ph-pts" v-if="points">{{ points }} 點</span>
      <a v-if="card.url" :href="card.url" target="__blank" rel="noopener"
         class="ph-link">查看 →</a>
    </div>
  </div>
</template>

<style>
.price-history {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 8px;
}
.ph-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ph-name { color: var(--text); font-size: 14px; }
.ph-tags {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ph-src { font-size: 11px; color: var(--text-3); }
.ph-badge { font-size: 12px; font-weight: 600; }
.ph-spark { margin: 8px 0 4px; }
.ph-no { color: var(--muted); font-size: 12px; }
.ph-foot {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  color: var(--text-2);
}
.ph-now { color: var(--text); font-weight: 600; font-size: 15px; }
.ph-link { margin-left: auto; color: var(--link); text-decoration: none; }
</style>
