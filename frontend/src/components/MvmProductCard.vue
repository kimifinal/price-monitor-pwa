<script setup>
// MvmProductCard.vue — ONE MVM 檔期品項卡。Pure renderer: draws orig→promo,
// the discount %, the type badge and the category from the baked JSON; it never
// re-derives a number. Colours resolve through the design-token SSOT (style.css);
// no raw hex (CI CSS-token guard + sloplint gate 48). Money renders via moneyTWD
// (TWD, no ".00" — issue #25). Discount tier + badge resolve through lib/mvm.js.
import { computed } from 'vue'
import { moneyTWD } from '../lib/format.js'
import { discountPct, discountTier, productBadge } from '../lib/mvm.js'

const props = defineProps({
  // a baked product: { sku, name, cat, type, orig, promo, discount, note? }
  product: { type: Object, required: true },
  // the catalog's price_types map (3 types); the card resolves its badge against it
  priceTypes: { type: Object, default: () => ({}) },
})

// moneyTWD(null) -> "TWD 0" is wrong for a missing figure, so blank-figures show
// "N/A" (sloplint gate 19 forbids "—" for an empty value).
const p = computed(() => props.product || {})
const origText = computed(() => (p.value.orig != null ? moneyTWD(p.value.orig) : 'N/A'))
const promoText = computed(() => (p.value.promo != null ? moneyTWD(p.value.promo) : 'N/A'))
const saveText = computed(() =>
  p.value.discount != null ? `省 ${moneyTWD(p.value.discount)}` : 'N/A',
)

// discount %: one decimal when computable, else null -> the card shows "N/A".
const pct = computed(() => discountPct(p.value))
const pctText = computed(() =>
  pct.value == null ? 'N/A' : `-${pct.value.toFixed(1)}%`,
)
// colour tier -> the design-token class the card paints (high/mid/low).
const discClass = computed(() => `disc-${discountTier(pct.value)}`)

// the type badge: label + colour keyed off priceTypes (sub-variants fall back base).
const badge = computed(() => productBadge(p.value, props.priceTypes))
const badgeKey = computed(() => `badge-${badge.value.key}`)
const catText = computed(() => p.value.cat || 'N/A')

// the "查看" link: a pure verb, no glued arrow (sloplint gate 63). MVM JSON has
// no url field, so this points at # (an honest placeholder the Tier-C image/URL
// pass will fill); the aria-label names the product for screen readers.
const linkHref = computed(() => (p.value.url ? p.value.url : '#'))
const linkLabel = computed(() => `檢視 ${p.value.name || '未命名品項'} 於好市多`)
const nameText = computed(() => p.value.name || '未命名品項')
const skuText = computed(() =>
  p.value.sku != null ? String(p.value.sku) : 'N/A',
)
const hasNote = computed(() => !!(p.value && p.value.note))
</script>

<template>
  <article class="mvm-card" :data-sku="skuText">
    <!-- 88x88 image slot: MVM JSON carries no image, so it is an honest
         placeholder (the SKU in mono + "圖片待補"), not a broken <img> (gate 76). -->
    <div class="mvm-img" aria-label="商品圖片佔位，MVM JSON 未含圖片">
      <span class="mvm-img-sku">{{ skuText }}</span>
      <span class="mvm-img-note">圖片待補</span>
    </div>

    <div class="mvm-body">
      <div class="mvm-top">
        <span class="mvm-cat">{{ catText }}</span>
        <span class="mvm-discount" :class="discClass">{{ pctText }}</span>
      </div>

      <h2 class="mvm-name">{{ nameText }}</h2>

      <div class="mvm-prices">
        <span class="mvm-orig" title="原價">{{ origText }}</span>
        <span class="mvm-promo">{{ promoText }}</span>
        <span class="mvm-save">{{ saveText }}</span>
      </div>

      <p v-if="hasNote" class="mvm-note">{{ product.note }}</p>

      <div class="mvm-card-foot">
        <span class="badge" :class="badgeKey" :data-badge="badge.key">
          {{ badge.label }}
        </span>
        <a
          class="mvm-link"
          :href="linkHref"
          target="_blank"
          rel="noopener"
          :aria-label="linkLabel"
          >查看</a
        >
      </div>
    </div>
  </article>
</template>

<style>
/* Colours ONLY as var(--token); CI guards raw 6-digit hex in .vue and
 * sloplint gate 48. Spacing on the 4px token grid (--sp-*). */
.mvm-card {
  display: flex;
  gap: var(--sp-3);
  background: var(--surface);
  color: var(--text); /* gate 41: card carries its own ink, not inherited */
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--sp-3);
  min-width: 0;
}
.mvm-img {
  flex: 0 0 88px;
  width: 88px;
  height: 88px;
  align-self: flex-start;
  background: var(--surface-1);
  border: 1px solid var(--border-2);
  border-radius: var(--radius-sm);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-1);
  color: var(--muted);
}
.mvm-img-sku {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--sku);
  font-variant-numeric: tabular-nums;
}
.mvm-img-note {
  font-size: 0.62rem;
  color: var(--muted);
}
.mvm-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.mvm-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--sp-2);
}
.mvm-cat {
  /* a category tag (gate 54 exception "category tag over a card"): body face,
   * NOT mono (gate 64 — mono is for figures/code, not labels). */
  font-family: var(--font-sans);
  font-size: 0.72rem;
  color: var(--text-2);
  background: var(--surface-1);
  padding: var(--sp-1) 8px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border);
}
.mvm-discount {
  font-family: var(--font-mono);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  font-size: 0.85rem;
}
.disc-high { color: var(--success); }
.disc-mid { color: var(--good-deal); }
.disc-low { color: var(--text-2); }
.mvm-name {
  /* h2: product title; sequence is h1 (catalog head) -> h2 (gate F21, no skip). */
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text);
  margin: 0;
  line-height: 1.3;
  overflow-wrap: break-word;
  min-width: 0;
}
.mvm-prices {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  margin: var(--sp-1) 0;
  flex-wrap: wrap;
}
.mvm-orig {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-3);
  text-decoration: line-through;
  font-variant-numeric: tabular-nums;
}
.mvm-promo {
  font-family: var(--font-mono);
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}
.mvm-save {
  font-size: 0.72rem;
  color: var(--good-deal);
}
.mvm-note {
  font-size: 0.72rem;
  color: var(--muted);
  margin: 0;
}
.mvm-card-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--sp-2);
  margin-top: auto;
  padding-top: var(--sp-2);
  flex-wrap: wrap;
}
.badge {
  /* gate 64: a label in the BODY face, one step smaller; NOT mono costume.
   * letter-spacing kept at 0.02em (<= 0.03em, gate 67). */
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 0.72rem;
  padding: var(--sp-1) 8px;
  border-radius: var(--radius-pill);
  border: 1px solid currentColor;
  line-height: 1.6;
  letter-spacing: 0.02em;
}
.badge-online_only { color: var(--link); }
.badge-store_online_diff { color: var(--good-deal); }
.badge-store_only { color: var(--sku); }
/* gate 63: the link text is a pure verb "查看" — no glued arrow. */
.mvm-link {
  font-family: var(--font-sans);
  font-size: 0.78rem;
  color: var(--link);
  text-decoration: none;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  white-space: nowrap;
  border-radius: var(--radius-sm);
  padding: 0 var(--sp-2);
}
/* gate 26b: full interactive states — hover / active / focus-visible / disabled,
 * token-driven (no raw hex). focus-visible doubles the ring at 3:1 on --accent-hover. */
.mvm-link:hover,
.mvm-cat:hover { text-decoration: none; }
.mvm-link:active { filter: brightness(1.12); }
.mvm-link:focus-visible {
  outline: 2px solid var(--accent-hover);
  outline-offset: 2px;
}
.mvm-link:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
