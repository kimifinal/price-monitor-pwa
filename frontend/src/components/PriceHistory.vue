<script setup>
// PriceHistory.vue — renders one product's price-history card: an SVG
// sparkline + a verdict badge ("歷史最低 / 接近高點 / ..."). It is a PURE
// renderer: it never re-derives the verdict — it imports priceVerdict +
// sparkPath from the single source of truth (monitor.js).
//
// Multi-source (crypto #3): the card is source-agnostic — a coingecko coin and a
// Costco item both flow through the SAME priceVerdict; only a small source badge
// (🪙 CoinGecko vs 🛒 costco) differs. So crypto "movement" renders with no new
// verdict logic.
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
const stroke = computed(() =>
  ({
    all_time_low: '#4caf50',
    good_deal: '#8bc34a',
    stable: '#b0a8c8',
    near_high: '#e6a23c',
    unknown: '#555',
  })[verdict.value.verdict] || '#b0a8c8',
)

const points = computed(() => props.card?.series?.length || props.card?.metrics?.points || 0)

// Multi-source badge: a coingecko coin wears a 🪙, everything else a 🛒. The
// verdict stays the single SSOT; only the label/icon differ per source.
const source = computed(() => props.card?.source || props.card?.tag || 'costco')
const isCrypto = computed(() => source.value === 'coingecko' || source.value === 'crypto')
const kindIcon = computed(() => (isCrypto.value ? '🪙' : '🛒'))
const sourceLabel = computed(() => (isCrypto.value ? 'CoinGecko' : source.value))
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
        <span class="ph-src" :class="{ 'ph-src--crypto': isCrypto }">{{ srcText }}</span>
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
  background: #141218;
  border: 1px solid #2a2740;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 8px;
}
.ph-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ph-name { color: #efeaff; font-size: 14px; }
.ph-tags {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ph-src { font-size: 11px; color: #8a86a8; }
.ph-src--crypto { color: #f0c000; font-weight: 600; }
.ph-badge { font-size: 12px; font-weight: 600; }
.ph-spark { margin: 8px 0 4px; }
.ph-no { color: #555; font-size: 12px; }
.ph-foot {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  color: #b0a8c8;
}
.ph-now { color: #efeaff; font-weight: 600; font-size: 15px; }
.ph-link { margin-left: auto; color: #8fb4ff; text-decoration: none; }
</style>
