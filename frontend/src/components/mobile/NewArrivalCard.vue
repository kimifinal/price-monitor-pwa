<template>
  <article
    class="na-card"
    role="button"
    tabindex="0"
    aria-label="查看這件新品"
    @click="open"
    @keydown.enter="open"
  >
    <!-- image slot: an honest line-icon placeholder + SKU caption. The baked
         costco-history JSON carries NO image (gate 76), so the slot mirrors
         MvmMobileProductCard's .m-card-img placeholder — never a faked picture. -->
    <div class="na-thumb" aria-label="商品圖片待補">
      <MobileIcon name="box" :size="30" />
      <span class="na-thumb-cap">{{ skuText }}</span>
    </div>

    <div class="na-body">
      <!-- discovery top row: a category chip (left) + a watch (心) toggle (right) -->
      <div class="na-top">
        <span v-if="tagText" class="na-cat">{{ tagText }}</span>
        <span class="na-spacer" aria-hidden="true" />
        <button
          type="button"
          class="na-heart"
          :class="{ 'is-on': watched }"
          :aria-pressed="watched"
          :aria-label="watched ? `已追蹤：${name}` : `加入追蹤：${name}`"
          @click.stop="toggleWatch"
        >
          <MobileIcon name="heart" :size="20" />
        </button>
      </div>

      <h3 class="na-name" :title="name">{{ name }}</h3>

      <!-- discovery tags: 上線 N 天 (primary) + 新到貨 / 省 $X / 歷史最低 (secondary,
           may coexist). Rebuilt from the numbers here, NEVER verdict.label (it
           carries emoji — gate 30a). -->
      <div class="na-tags">
        <span class="na-tag na-online">{{ onlineLabel }}</span>
        <span v-for="b in badges" :key="b" class="na-tag" :class="badgeClass(b)">{{ b }}</span>
      </div>

      <div class="na-price">
        <span class="na-now"><span class="na-currency">$</span>{{ currentText }}</span>
        <span v-if="hasDrop" class="na-was" :title="`原價 $${wasText}`">was ${{ wasText }}</span>
      </div>

      <!-- low ~ high spread (gate 19: N/A, never an em/en dash) -->
      <p v-if="rangeText" class="na-range">{{ rangeText }}</p>
    </div>
  </article>
</template>

<script setup>
// NewArrivalCard.vue — ONE 探索導向 新品卡 for the 新品 tab (#48). NOT the
// 省錢-driven MvmMobileProductCard: the headline is 上線時間 / 新到貨 / 歷史最低;
// 省錢 is only a secondary 省 $X chip when drop_pct_from_high > 0. No 約X折
// headline, no 通路對比. Money groups through formatTWD (the TWD SSOT, #25) with
// a "$" prefix. Colours resolve ONLY through the warm token scope var(--m-*) —
// no raw hex (sloplint gate 48 / CI css-token guard). Missing figures read "N/A",
// never "—" (gate 19). No emoji anywhere (gate 30a).
import { ref, computed } from 'vue'
import MobileIcon from './MobileIcon.vue'
import { formatTWD } from '../../lib/format.js'
import { newArrivalTags, savingsAmount } from '../../lib/newarrivals.js'

const props = defineProps({
  // a raw costco-history item: sku/name/tag/current/low/high/drop_pct_from_high/
  // at_all_time_low/first_seen/verdict.
  item: { type: Object, default: null },
  // reference moment for the 上線 N 天 / 新到貨 badges (tests pass a fixed date).
  refDate: { type: [Date, String], default: undefined },
})

const emit = defineEmits(['open', 'watch'])

// The card binds to a safe object so a null item can't crash a render.
const item = computed(() =>
  props.item && typeof props.item === 'object' ? props.item : {},
)

// the heart watch toggle (visual only this pass; no persistence yet — mirrors the
// MvmMobileProductCard wish toggle). aria-pressed reflects the state (a11y).
const watched = ref(false)
function toggleWatch() {
  watched.value = !watched.value
  emit('watch', { item: props.item, watched: watched.value })
}
function open() {
  if (props.item) emit('open', props.item)
}

function num(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

const name = computed(() => {
  const n = item.value.name
  return typeof n === 'string' && n.trim() ? n : '未命名商品'
})
const tagText = computed(() => {
  const t = item.value.tag
  return typeof t === 'string' && t.trim() ? t : ''
})
const skuText = computed(() => {
  const s = item.value.sku
  return s != null ? String(s) : 'N/A'
})

// 現價 (gate 19: N/A, never —).
const currentText = computed(() => {
  const n = num(item.value.current)
  return n == null ? 'N/A' : formatTWD(n)
})

// 最低 / 最高 (gate 19).
const lowNum = computed(() => num(item.value.low))
const highNum = computed(() => num(item.value.high))
const lowText = computed(() => (lowNum.value == null ? 'N/A' : formatTWD(lowNum.value)))
const highText = computed(() => (highNum.value == null ? 'N/A' : formatTWD(highNum.value)))
// the low ~ high spread only when there is a real range (avoids a redundant
// "$x ~ $x" when low === high). Returns the full label, or '' when absent.
const rangeText = computed(() => {
  const lo = lowNum.value
  const hi = highNum.value
  if (lo == null || hi == null || lo === hi) return ''
  return `最低 $${lowText.value} · 最高 $${highText.value}`
})

// 省 $X: a positive drop from the all-time high — a SECONDARY signal (not the
// headline, so it shows only when drop_pct_from_high > 0).
const hasDrop = computed(() => savingsAmount(props.item) > 0)
const wasText = computed(() => {
  const hi = highNum.value
  return hi == null ? 'N/A' : formatTWD(hi)
})

// Rebuild the discovery badges here (emoji-free) instead of rendering verdict.label.
const tagBag = computed(() => newArrivalTags(props.item, props.refDate))
const onlineLabel = computed(() => tagBag.value.online)
const badges = computed(() => tagBag.value.badges)

function badgeClass(b) {
  if (b === '新到貨') return 'na-new'
  if (b.startsWith('省 $')) return 'na-save'
  if (b === '歷史最低') return 'na-low'
  return 'na-other'
}
</script>

<style scoped>
/* Colours resolve ONLY through the warm token scope var(--m-*) — no raw hex
   (sloplint gate 48 / CI css-token guard). Spacing on the shared 4px grid
   (--sp-*), radius on --radius-*, fonts on --font-*. Scoped so these rules match
   only this component's nodes and never bleed onto the dark catalog. No emoji
   (gate 30a): the tags are rebuilt from the numbers, never from verdict.label. */
.na-card {
  display: flex;
  gap: var(--sp-3);
  background: var(--m-card);
  color: var(--m-ink); /* gate 41: a card carries its own warm ink */
  border: 1px solid var(--m-hairline);
  border-radius: var(--radius-lg);
  padding: var(--sp-3);
  min-width: 0;
  box-shadow: 0 1px 2px var(--m-shadow);
  cursor: pointer;
  transition: transform 120ms ease, box-shadow 120ms ease;
}
.na-card:active {
  transform: scale(0.995);
}
.na-card:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}

/* image slot: an honest placeholder (the baked JSON has no image, gate 76). */
.na-thumb {
  flex: 0 0 92px;
  width: 92px;
  height: 92px;
  border-radius: var(--radius);
  background: var(--m-soft);
  border: 1px solid var(--m-hairline);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  color: var(--m-muted);
}
.na-thumb .m-ico {
  width: 30px;
  height: 30px;
  opacity: 0.6;
}
.na-thumb-cap {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 0.62rem;
  color: var(--m-muted);
}

.na-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.na-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-2);
}
.na-cat {
  flex: 0 0 auto;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--m-ink-2);
  background: var(--m-soft);
  border: 1px solid var(--m-hairline);
  border-radius: var(--radius-pill);
  padding: 2px 9px;
  line-height: 1.3;
}
.na-spacer {
  flex: 1;
}
/* watch toggle: a 44px min touch target (gate 39b). */
.na-heart {
  flex: 0 0 auto;
  width: 44px;
  height: 44px;
  min-width: 44px;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--m-hairline);
  background: var(--m-card);
  color: var(--m-muted);
  cursor: pointer;
  border-radius: var(--radius-pill);
  touch-action: manipulation;
  transition: background 120ms ease, color 120ms ease, transform 120ms ease;
}
.na-heart:active {
  transform: scale(0.92);
}
.na-heart.is-on {
  color: var(--m-price);
}
.na-heart.is-on .m-ico {
  fill: var(--m-price);
  stroke: var(--m-price);
}
.na-heart:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}
.na-heart svg {
  width: 20px;
  height: 20px;
}

.na-name {
  margin: var(--sp-2) 0 0;
  font-size: 0.92rem;
  font-weight: 600;
  line-height: 1.35;
  color: var(--m-ink);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 2.5em;
}

/* discovery tags: 上線 (warm gold, primary) + secondary 新到貨 / 省 / 歷史最低 */
.na-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: var(--sp-2);
}
.na-tag {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 3px 9px;
  border-radius: var(--radius-pill);
  line-height: 1.2;
  white-space: nowrap;
}
/* 上線時間 — warm gold (calendar / freshness semantics). */
.na-online {
  color: var(--m-online-ink);
  background: var(--m-online-bg);
  border: 1px solid var(--m-hairline);
  font-weight: 700;
}
/* 新到貨 — brand-red freshness on neutral cream. */
.na-new {
  color: var(--m-price);
  background: var(--m-soft);
}
/* 歷史最低 — good-green on neutral cream. */
.na-low {
  color: var(--m-good);
  background: var(--m-soft);
  border: 1px solid var(--m-good);
}
/* 省 $X — neutral warm secondary (savings is NOT the headline). */
.na-save {
  color: var(--m-save-ink);
  background: var(--m-save-bg);
}
.na-other {
  color: var(--m-ink-2);
  background: var(--m-soft);
}

/* price: 現價 big, was struck (drop only), low ~ high spread */
.na-price {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  margin-top: auto;
  padding-top: var(--sp-2);
}
.na-now {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 1.35rem;
  font-weight: 800;
  color: var(--m-price);
  line-height: 1;
  display: inline-flex;
  align-items: baseline;
}
.na-currency {
  font-size: 0.85rem;
  margin-right: 1px;
}
.na-was {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 0.8rem;
  color: var(--m-muted);
  text-decoration: line-through;
}
.na-range {
  margin: 4px 0 0;
  font-size: 0.72rem;
  color: var(--m-ink-3);
  font-variant-numeric: tabular-nums;
}

/* Reduced-motion: kill the micro-transitions (prefers-reduced-motion guard). */
@media (prefers-reduced-motion: reduce) {
  .na-card,
  .na-heart {
    transition: none;
  }
}
</style>
