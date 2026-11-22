<script setup>
// CatalogProductCard.vue — ONE 暖色 全部商品 全庫品項卡 (案 #50).
//
// A pure renderer over the baked catalog.json: it never re-derives a price. The
// "約 X 折" badge comes from zheOfCatalog (lib/catalog.js, price→basePrice, the
// 個位 折, e.g. 121/1000→1, 5199/6899→8); the 省 badge from saveText; the last
// line from catalogPriceLine (`買場 $X` / `線上 $X` / `買場 $base · 線上 $price`).
// Money groups through formatTWD (the TWD SSOT, issue #25) with a "$" prefix,
// matching the mockup (not "TWD "). Colours resolve ONLY through the warm token
// scope var(--m-*) — no raw hex (sloplint gate 48 / CI css-token guard). Missing
// figures read "N/A", never "—" (gate 19). The image slot is an honest line-icon
// placeholder (the baked catalog has no image, gate 76). No emoji anywhere (30a).
//
// MODE (#50): in 'online' mode a discounted item's main price takes a blue tint
// (var(--m-zhe-ink)) instead of the default red, and a 網路獨家 item shows the
// orange "僅限線上" badge. In 'store' mode the main price is the red 買場 price.
import { ref, computed } from 'vue'
import MobileIcon from './MobileIcon.vue'
import {
  isOnlineOnly,
  zheOfCatalog,
  saveText,
  mainPrice,
  catalogPriceLine,
} from '../../lib/catalog.js'
import { formatTWD } from '../../lib/format.js'

const props = defineProps({
  // a baked catalog item: { sku, name, price, basePrice, discount, online_only, stock }
  product: { type: Object, required: true },
  // the active 買場/線上 toggle: 'store' (default) or 'online'
  mode: { type: String, default: 'store' },
})

// The whole card binds to this so a null product can't crash a render.
const p = computed(() => (props.product && typeof props.product === 'object' ? props.product : {}))

// A missing figure is "N/A" (gate 19), not "—" and not a bogus $0.
const money = (n) => (n == null ? 'N/A' : '$' + formatTWD(n))
const nameText = computed(() => (p.value.name || '未命名品項'))
const skuText = computed(() => (p.value.sku != null ? String(p.value.sku) : 'N/A'))

// The main price (large). Red by default; a blue tint in online mode when the
// item is discounted (price < basePrice) — the "this 線上 促價 is cheaper" cue.
const promoText = computed(() => money(mainPrice(p.value, props.mode)))
const discounted = computed(() => {
  const price = p.value.price
  const base = p.value.basePrice
  return price != null && base != null && price < base
})
const priceIsBlue = computed(() => props.mode === 'online' && discounted.value)

// The struck original price, shown only when it differs from the main price.
const showOrig = computed(() => {
  const price = p.value.price
  const base = p.value.basePrice
  return base != null && price != null && base !== price
})
const origText = computed(() => money(p.value.basePrice))

// "約 X 折" — the 個位 折 from zheOfCatalog; null (a missing/≤0 figure, or no
// discount) hides the chip.
const zhe = computed(() => zheOfCatalog(p.value))
const zheText = computed(() => (zhe.value == null ? '' : `約 ${zhe.value} 折`))

// "省 $X" — from saveText; '' (no positive discount) hides the chip.
const save = computed(() => saveText(p.value))

// the orange "僅限線上" badge — only in online mode, only for a 網路獨家 item.
const showOnlineBadge = computed(() => props.mode === 'online' && isOnlineOnly(p.value))

// the card's last line: 買場/線上 (or 買場/線上 two-figure) per catalogPriceLine.
const lineText = computed(() => catalogPriceLine(p.value, props.mode))

// the heart wish toggle (visual only in this pass; no persistence yet).
const wished = ref(false)
function toggleWish() {
  wished.value = !wished.value
}
</script>

<template>
  <article class="m-cat-card" :data-sku="skuText">
    <!-- image slot: an honest line-icon placeholder + SKU caption (gate 76) -->
    <div class="m-cat-img" aria-hidden="true">
      <MobileIcon name="box" />
    </div>

    <div class="m-cat-body">
      <div class="m-cat-top">
        <h2 class="m-cat-name">{{ nameText }}</h2>
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

      <div class="m-cat-prices">
        <span class="m-cat-promo" :class="{ 'is-blue': priceIsBlue }">{{ promoText }}</span>
        <span v-if="showOrig" class="m-cat-orig">{{ origText }}</span>
      </div>

      <div class="m-cat-badges">
        <span v-if="save" class="m-cat-badge m-cat-badge-save">{{ save }}</span>
        <span v-if="zheText" class="m-cat-badge m-cat-badge-zhe">{{ zheText }}</span>
        <span v-if="showOnlineBadge" class="m-cat-badge m-cat-badge-online">僅限線上</span>
      </div>

      <p class="m-cat-line">{{ lineText }}</p>
    </div>
  </article>
</template>

<style scoped>
/* Colours RESOLVE ONLY through the warm token scope var(--m-*) — no raw hex, so
 * the CI css-token guard + sloplint gate 48 stay clean on this component.
 * Spacing on the shared 4px grid; radius on the shared --radius-*. */
.m-cat-card {
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
.m-cat-img {
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
.m-cat-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.m-cat-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-2);
}
.m-cat-name {
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
/* gate 26b: three-state interactive feedback; border-width stays constant. */
.m-heart:active {
  transform: scale(0.94);
}
.m-heart:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}

.m-cat-prices {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  flex-wrap: wrap;
}
.m-cat-promo {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--m-price);
}
/* online-mode discounted cue: the 促價 takes the zhe blue instead of red */
.m-cat-promo.is-blue {
  color: var(--m-zhe-ink);
}
.m-cat-orig {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 0.8rem;
  color: var(--m-muted);
  text-decoration: line-through;
}
.m-cat-badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-1);
}
.m-cat-badge {
  /* gate 64: a label in the body face, one step smaller, not mono costume. */
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 0.72rem;
  line-height: 1.6;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  white-space: nowrap;
}
.m-cat-badge-save {
  color: var(--m-save-ink);
  background: var(--m-save-bg);
}
.m-cat-badge-zhe {
  color: var(--m-zhe-ink);
  background: var(--m-zhe-bg);
}
.m-cat-badge-online {
  color: var(--m-online-ink);
  background: var(--m-online-bg);
}
.m-cat-line {
  font-size: 0.75rem;
  color: var(--m-ink-2);
  margin: 0;
  font-variant-numeric: tabular-nums;
}
</style>
