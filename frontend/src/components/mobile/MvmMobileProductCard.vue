<script setup>
// MvmMobileProductCard.vue — ONE 暖色 MVM 檔期品項卡 (案 B / #49).
//
// A pure renderer over the baked JSON: it never re-derives a price. The
// "約 X 折" badge comes from zheOf (lib/mvm.js, the 個位 折, e.g. 121/1000→1,
// 329/349→9); the card last line comes from priceLine (`買場 $X · 線上 $Y` or
// `買場 $X · 買場 $Y`). Money groups through formatTWD (the TWD SSOT, issue #25)
// with a "$" prefix, matching the mockup (not "TWD "). Colours resolve ONLY
// through the warm token scope var(--m-*) — no raw hex (sloplint gate 48 / CI
// css-token guard). Missing figures read "N/A", never "—" (sloplint gate 19).
// The image slot is an honest line-icon placeholder (the baked JSON has no image,
// gate 76); the SKU sits in mono as the caption. No emoji anywhere (gate 30a).
import { ref, computed } from 'vue'
import MobileIcon from './MobileIcon.vue'
import { zheOf, priceLine, productBadge } from '../../lib/mvm.js'
import { formatTWD } from '../../lib/format.js'

const props = defineProps({
  // a baked product: { sku, name, cat, type, orig, promo, discount, note? }
  product: { type: Object, required: true },
  // the catalog's price_types map (unused for the mobile badge short-label, kept
  // for parity with the dark card + a future type chip)
  priceTypes: { type: Object, default: () => ({}) },
  // the active 檔期's price_type, so a typeless store-only item resolves the
  // store-form last line (買場 · 買場) via priceLine.
  tabPriceType: { type: String, default: '' },
  // the active 檔期's 到期日 ("MM/DD", or 'N/A'), shown as a "到 MM/DD" chip
  endDate: { type: String, default: '' },
})

// The whole card binds to this so a null product can't crash a render.
const p = computed(() => (props.product && typeof props.product === 'object' ? props.product : {}))

// A missing figure is "N/A" (gate 19), not "—" and not a bogus $0.
const money = (n) => (n == null ? 'N/A' : '$' + formatTWD(n))
const promoText = computed(() => money(p.value.promo))
const origText = computed(() => money(p.value.orig))
const saveText = computed(() => (p.value.discount != null ? `省 $${formatTWD(p.value.discount)}` : ''))
const nameText = computed(() => p.value.name || '未命名品項')
const skuText = computed(() => (p.value.sku != null ? String(p.value.sku) : 'N/A'))

// "約 X 折" — the 個位 折 from zheOf; null (a missing/≤0 figure) hides the chip.
const zhe = computed(() => zheOf(p.value))
const zheText = computed(() => (zhe.value == null ? '' : `約 ${zhe.value} 折`))

// card last line — the 買場/線上 (or 買場/買場) figure.
const lineText = computed(() => priceLine(p.value, props.tabPriceType))

// The 到期日 chip only renders when the tab actually carries a date.
// Kimi 2026-11-22: the range form "MM/DD ~ MM/DD" (no "到 " prefix, it IS
// the range) vs. the old "MM/DD" form (kept as "到 MM/DD" backward-compat).
// A "敬請期待"/N-A/empty period hides the chip — a no-date 檔期 shows nothing
// extra on the card, only in the slider chip below.
const endDateShown = computed(() => {
  const s = String(props.endDate || '')
  if (!s || s === 'N/A' || s === '敬請期待') return ''
  return s.includes('~') ? s : `到 ${s}`
})

// a decorative type chip (store_online_diff → "【賣場售價】"); skipped for the
// long-only labels so the chip row stays legible on a narrow card.
const badge = computed(() => productBadge(p.value, props.priceTypes))
const typeChip = computed(() => {
  const b = badge.value
  if (b.key === 'store_online_diff') return '【賣場售價】'
  return ''
})

// the heart wish toggle (visual only in this pass; no persistence yet).
const wished = ref(false)
function toggleWish() {
  wished.value = !wished.value
}
</script>

<template>
  <article class="m-card" :data-sku="skuText">
    <!-- image slot: an honest line-icon placeholder + SKU caption (gate 76) -->
    <div class="m-card-img" aria-hidden="true">
      <MobileIcon name="box" />
    </div>

    <div class="m-card-body">
      <div class="m-card-top">
        <h2 class="m-card-name">{{ nameText }}</h2>
        <button
          class="m-heart"
          type="button"
          :class="{ 'is-wished': wished }"
          :aria-pressed="wished"
          :aria-label="wished ? `已加入專屬清單：${nameText}` : `加入專屬清單：${nameText}`"
          @click="toggleWish"
        >
          <MobileIcon name="heart" />
        </button>
      </div>

      <div class="m-card-prices">
        <span class="m-card-promo">{{ promoText }}</span>
        <span v-if="p.orig != null" class="m-card-orig">{{ origText }}</span>
      </div>

      <div class="m-card-badges">
        <span v-if="saveText" class="m-badge m-badge-save">{{ saveText }}</span>
        <span v-if="zheText" class="m-badge m-badge-zhe">{{ zheText }}</span>
        <span v-if="typeChip" class="m-badge m-badge-type">{{ typeChip }}</span>
        <span v-if="endDateShown" class="m-badge m-badge-date">{{ endDateShown }}</span>
      </div>

      <p class="m-card-line">{{ lineText }}</p>
    </div>
  </article>
</template>

<style>
/* Colours RESOLVE ONLY through the warm token scope var(--m-*) — no raw hex, so
 * the CI css-token guard + sloplint gate 48 stay clean on this component.
 * Spacing on the shared 4px grid; radius on the shared --radius-*. */
.m-card {
  display: flex;
  gap: var(--sp-3);
  background: var(--m-card);
  color: var(--m-ink); /* gate 41: a card carries its own warm ink */
  border: 1px solid var(--m-hairline);
  border-radius: var(--radius-lg);
  padding: var(--sp-4);
  min-width: 0;
  box-shadow: 0 1px 2px var(--m-shadow);
}
.m-card-img {
  flex: 0 0 72px;
  width: 72px;
  height: 72px;
  align-self: flex-start;
  background: var(--m-soft);
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--m-muted);
}
.m-card-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.m-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-2);
}
.m-card-name {
  /* h2: the product title; the catalog head is h1 (gate F21, no skip). */
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--m-ink);
  margin: 0;
  line-height: 1.3;
  overflow-wrap: break-word;
  min-width: 0;
}
.m-heart {
  flex: 0 0 auto;
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--m-hairline);
  border-radius: var(--radius-pill);
  background: var(--m-card);
  color: var(--m-muted);
  cursor: pointer;
  padding: 0;
}
.m-heart .m-ico {
  width: 20px;
  height: 20px;
}
.m-heart.is-wished {
  color: var(--m-price);
  border-color: var(--m-price);
}
.m-heart.is-wished .m-ico {
  fill: var(--m-price);
  stroke: var(--m-price);
}
/* gate 26b: three-state interactive feedback; border-width stays constant, the
 * wish state moves to colour + fill (gate 39a). */
.m-heart:active {
  transform: scale(0.94);
}
.m-heart:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}
.m-heart:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.m-card-prices {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  flex-wrap: wrap;
}
.m-card-promo {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--m-price);
}
.m-card-orig {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 0.8rem;
  color: var(--m-muted);
  text-decoration: line-through;
}
.m-card-badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-1);
}
.m-badge {
  /* gate 64: a label in the body face, one step smaller, not mono costume. */
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 0.72rem;
  line-height: 1.6;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  white-space: nowrap;
}
.m-badge-save {
  color: var(--m-save-ink);
  background: var(--m-save-bg);
}
.m-badge-zhe {
  color: var(--m-zhe-ink);
  background: var(--m-zhe-bg);
}
.m-badge-type {
  color: var(--m-date-ink);
  background: var(--m-date-bg);
}
.m-badge-date {
  color: var(--m-date-ink);
  background: var(--m-date-bg);
}
.m-card-line {
  font-size: 0.75rem;
  color: var(--m-ink-2);
  margin: 0;
  font-variant-numeric: tabular-nums;
}
</style>
