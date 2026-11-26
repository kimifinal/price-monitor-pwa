<script setup>
// ProductDetail.vue — the 暖色 商品詳情頁 (#53), the detail view reached by
// clicking a browse card (案 #49/#50). A PURE renderer over lib/detail.js: every
// figure / badge / note / the 到官網 URL is decided there, never re-derived here.
//
// Layout mirrors the approved v1 mockup (mockups/product-detail.html), top→bottom:
//   1. sticky appbar: 完成 back (品牌紅) · 商品詳情 title (sun line-icon) ·
//      分享 + 加入追蹤 44px 圓形鈕 (追蹤 active → 品牌紅).
//   2. product image card (a line-icon placeholder — the baked catalog has no
//      image, the same honesty as the catalog card's box icon, gate 76).
//   3. 商品名 (h1, balanced wrap) + 商品編號 SKU (mono, tabular-nums).
//   4. 賣場 price section (--m-save 紅底 icon): 現價 + 原價 strike + 省/到/約折
//      badges + a 會員護照價 note.
//   5. 線上 price section (--m-online 橘底 icon): 現價 (+ 僅限線上 badge, a
//      價格不對？ verify) + 原價 strike + badges + a 缺貨/現貨 note.
//   6. a dashed divider.
//   7. 規格摘要 2-col grid (吸力/重量/使用時間/濾網) — PLACEHOLDER values (the
//      baked catalog carries no 規格 columns; lib/detail.specList fills "待補").
//   8. a fixed bottom CTA bar: 下次特價通知我 (primary, 品牌紅, bell) +
//      到官網看 (secondary outline, 外連 icon, a real <a> to 好市多 TW).
//
// Style guards honoured: colours resolve ONLY through the warm token scope
// var(--m-*) — NO raw hex (the CI css-token guard + sloplint gate 48). Icons are
// MobileIcon line-glyphs, NOT emoji (gate 30a). Every interactive control is a
// ≥44px touch target (the global style.css floor + the mockup's 44px buttons).
// Motion is covered by #22's global prefers-reduced-motion guard in style.css.
// The view is a pure renderer over baked JSON, so it loads fully OFFLINE.
import { ref, computed } from 'vue'
import MobileIcon from './MobileIcon.vue'
import { buildDetailModel, money, saveTextOf } from '../../lib/detail.js'

const props = defineProps({
  // the item being viewed — a catalog.json OR mvm.json item (detail.js
  // normalizes both shapes). A null product can't crash a render.
  product: { type: Object, required: true },
  // the active 檔期 range ("MM/DD ~ MM/DD" or a bare "MM/DD"); '' / 'N/A' hides
  // the 到 chip (a no-date 檔期 shows nothing extra).
  endDate: { type: String, default: '' },
})

const emit = defineEmits(['back', 'notify', 'share', 'verify', 'toggle-track', 'open-web'])

// The pure detail model (null-safe, shape-agnostic). One recompute per prop change.
const m = computed(() => buildDetailModel(props.product, { endDate: props.endDate }))

// Display text (money reuses the TWD SSOT via lib/detail.money).
const nameText = computed(() => m.value.name)
const skuText = computed(() => m.value.sku)

const storeNow = computed(() => money(m.value.store.now))
const storeOrig = computed(() => money(m.value.store.orig))
// strike the 原價 only when it differs from the 現價 (an undiscounted item hides it)
const showStoreOrig = computed(
  () =>
    m.value.store.orig != null &&
    m.value.store.now != null &&
    m.value.store.orig !== m.value.store.now,
)

const onlineNow = computed(() => money(m.value.online.now))
const onlineOrig = computed(() => money(m.value.online.orig))
const showOnlineOrig = computed(
  () =>
    m.value.online.orig != null &&
    m.value.online.now != null &&
    m.value.online.orig !== m.value.online.now,
)
// the 線上 現價 takes the 約 X 折 blue tint when discounted / 網路獨家 (the mockup's
// blue 線上 figure), else the default red 促價.
const onlineIsBlue = computed(
  () =>
    m.value.online.onlineOnly ||
    (m.value.online.now != null &&
      m.value.online.orig != null &&
      m.value.online.now < m.value.online.orig),
)

// badges: 省 (red, reused saveText SSOT) · 到 MM/DD (yellow) · 約 X 折 (blue).
const saveChip = computed(() => saveTextOf(props.product))
const zheChip = computed(() => (m.value.zhe == null ? '' : `約 ${m.value.zhe} 折`))
const dateChip = computed(() => m.value.endDate)

// 規格摘要 grid — placeholder "待補" values until a backend 規格 column exists.
const specs = computed(() => m.value.specs)
const specsPlaceholder = computed(() => specs.value.some((s) => s.placeholder))
const webUrl = computed(() => m.value.webUrl)

// Local, visual-only toggles (the same pattern as the cards' wish toggle — no
// persistence yet); each also emits so a parent can react.
const tracked = ref(false)
function toggleTrack() {
  tracked.value = !tracked.value
  emit('toggle-track', tracked.value)
}
const notified = ref(false)
function notify() {
  notified.value = !notified.value
  emit('notify', notified.value)
}
async function share() {
  // Best-effort native share; fall back to an emit so a parent / test can react
  // when navigator.share is absent (jsdom, older browsers).
  try {
    if (typeof navigator !== 'undefined' && navigator.share) {
      await navigator.share({ title: nameText.value, url: webUrl.value })
    } else {
      emit('share', webUrl.value)
    }
  } catch {
    emit('share', webUrl.value)
  }
}
function verify() {
  emit('verify', props.product)
}
function openWeb() {
  emit('open-web', webUrl.value)
}
</script>

<template>
  <div class="detail" data-detail-view>
    <!-- 1. top appbar: 完成 · 商品詳情 · 分享 / 追蹤 -->
    <header class="detail-appbar" data-detail-appbar>
      <button class="detail-back" type="button" aria-label="返回瀏覽" @click="emit('back')">
        <MobileIcon name="back" :size="20" />
        完成
      </button>
      <div class="detail-title">
        <MobileIcon name="sun" :size="20" class="detail-title-ico" aria-hidden="true" />
        商品詳情
      </div>
      <div class="detail-actions">
        <button
          class="detail-action-btn"
          type="button"
          aria-label="分享"
          data-share
          @click="share"
        >
          <MobileIcon name="share" :size="20" aria-hidden="true" />
        </button>
        <button
          class="detail-action-btn"
          :class="{ 'is-active': tracked }"
          type="button"
          :aria-pressed="tracked"
          :aria-label="`加入追蹤：${nameText}`"
          data-track
          @click="toggleTrack"
        >
          <MobileIcon name="heart" :size="20" aria-hidden="true" />
        </button>
      </div>
    </header>

    <!-- scrollable content -->
    <main class="detail-body" data-detail-body>
      <!-- 2. product image (line-icon placeholder; the baked catalog has no image) -->
      <div class="detail-img-card" data-detail-image>
        <div class="detail-img-placeholder" aria-label="商品圖片待補">
          <MobileIcon name="box" :size="80" aria-hidden="true" />
        </div>
      </div>

      <!-- 3. 商品名 + SKU -->
      <h1 class="detail-name" data-detail-name>{{ nameText }}</h1>
      <p class="detail-sku" data-detail-sku>商品編號 {{ skuText }}</p>

      <!-- 4. 賣場 price section -->
      <section class="detail-price-section" data-section-store>
        <div class="detail-price-header">
          <span class="detail-price-icon detail-price-icon--store" aria-hidden="true">
            <MobileIcon name="store" :size="14" aria-hidden="true" />
          </span>
          <span class="detail-price-label">賣場</span>
        </div>
        <div class="detail-price-row">
          <span class="detail-price-main" data-store-now>{{ storeNow }}</span>
          <span v-if="showStoreOrig" class="detail-price-orig">{{ storeOrig }}</span>
        </div>
        <div class="detail-price-badges">
          <span v-if="saveChip" class="badge badge--save">{{ saveChip }}</span>
          <span v-if="dateChip" class="badge badge--date">{{ dateChip }}</span>
          <span v-if="zheChip" class="badge badge--zhe">{{ zheChip }}</span>
        </div>
        <p class="detail-price-note">{{ m.store.note }}</p>
      </section>

      <!-- 5. 線上 price section -->
      <section class="detail-price-section" data-section-online>
        <div class="detail-price-header">
          <span class="detail-price-icon detail-price-icon--online" aria-hidden="true">
            <MobileIcon name="globe" :size="14" aria-hidden="true" />
          </span>
          <span class="detail-price-label">線上</span>
          <span
            v-if="m.online.onlineOnly"
            class="badge badge--online-only detail-online-badge"
          >僅限線上</span>
        </div>
        <div class="detail-price-row">
          <span class="detail-price-main" :class="{ 'is-blue': onlineIsBlue }" data-online-now>
            {{ onlineNow }}
          </span>
          <span v-if="showOnlineOrig" class="detail-price-orig">{{ onlineOrig }}</span>
          <button
            class="detail-price-verify"
            type="button"
            data-verify
            @click="verify"
          >價格不對？</button>
        </div>
        <div class="detail-price-badges">
          <span v-if="saveChip" class="badge badge--save">{{ saveChip }}</span>
          <span v-if="dateChip" class="badge badge--date">{{ dateChip }}</span>
          <span v-if="zheChip" class="badge badge--zhe">{{ zheChip }}</span>
        </div>
        <p class="detail-price-note">{{ m.online.note }}</p>
      </section>

      <!-- 6. dashed divider -->
      <hr class="detail-divider" />

      <!-- 7. 規格摘要 (placeholder until a backend 規格 column exists) -->
      <section class="detail-price-section" data-section-specs>
        <div class="detail-price-header detail-specs-header">
          <span class="detail-price-label detail-specs-title">規格摘要</span>
        </div>
        <div class="detail-specs">
          <div v-for="s in specs" :key="s.key" class="detail-spec">
            <div class="detail-spec-label">{{ s.label }}</div>
            <div class="detail-spec-value" :data-placeholder="s.placeholder ? 'true' : 'false'">
              {{ s.value }}
            </div>
          </div>
        </div>
        <p v-if="specsPlaceholder" class="detail-price-note detail-specs-note">
          規格欄待補，後端補欄後同步。
        </p>
      </section>
    </main>

    <!-- 8. fixed bottom CTA bar -->
    <div class="detail-cta" data-detail-cta>
      <button
        class="detail-cta-btn detail-cta-btn--primary"
        :class="{ 'is-active': notified }"
        type="button"
        data-notify
        @click="notify"
      >
        <MobileIcon name="bell" :size="18" aria-hidden="true" />
        {{ notified ? '已設通知 · 下次特價提醒你' : '下次特價通知我' }}
      </button>
      <a
        class="detail-cta-btn detail-cta-btn--secondary"
        :href="webUrl"
        target="_blank"
        rel="noopener noreferrer"
        data-open-web
        @click="openWeb"
      >
        <MobileIcon name="external" :size="16" aria-hidden="true" />
        到官網看
      </a>
    </div>
  </div>
</template>

<style scoped>
/* Colours resolve ONLY through the warm token scope var(--m-*) — no raw hex, so
 * the CI css-token guard + sloplint gate 48 stay clean. Spacing on the shared 4px
 * grid (--sp-*), radius on the shared --radius-*. SCOPED so these rules never
 * leak onto the dark PWA or the warm cards. */
.detail {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  flex-direction: column;
  background: var(--m-bg);
  color: var(--m-ink);
  font-family: var(--font-sans);
}

/* 1. top appbar */
.detail-appbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4);
  padding-top: max(var(--sp-3), env(safe-area-inset-top, 0px));
  background: var(--m-card);
  border-bottom: 1px solid var(--m-hairline);
  flex: 0 0 auto;
}
.detail-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: none;
  color: var(--m-brand);
  font-family: var(--font-sans);
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  padding: var(--sp-1);
  border-radius: var(--radius);
}
.detail-back:active {
  filter: brightness(1.15);
}
.detail-back:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}
.detail-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--m-ink);
  flex: 1;
  min-width: 0;
}
.detail-title-ico {
  color: var(--m-warm);
  flex: 0 0 auto;
}
.detail-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
}
.detail-action-btn {
  width: 44px;
  height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--m-hairline);
  border-radius: var(--radius-pill);
  background: var(--m-card);
  color: var(--m-ink-2);
  cursor: pointer;
  padding: 0;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.detail-action-btn:active {
  transform: scale(0.96);
}
.detail-action-btn:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}
.detail-action-btn.is-active {
  color: var(--m-price);
  border-color: var(--m-price);
}
.detail-action-btn.is-active .m-ico {
  fill: var(--m-price);
  stroke: var(--m-price);
}

/* 2-7. scrollable content */
.detail-body {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: var(--sp-4);
  padding-bottom: calc(var(--sp-8) + 80px); /* clear the fixed CTA bar */
}
.detail-img-card {
  background: var(--m-card);
  border: 1px solid var(--m-hairline);
  border-radius: var(--radius-xl);
  padding: var(--sp-6);
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 240px;
  margin-bottom: var(--sp-4);
  box-shadow: 0 2px 8px var(--m-shadow);
}
.detail-img-placeholder {
  width: 160px;
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--m-muted);
}
.detail-img-placeholder .m-ico {
  opacity: 0.3;
}

/* 3. name + SKU */
.detail-name {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--m-ink);
  line-height: 1.4;
  margin: 0 0 var(--sp-1);
  text-wrap: balance;
}
.detail-sku {
  font-size: 0.8rem;
  color: var(--m-muted);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  margin: 0 0 var(--sp-4);
}

/* 4-5. price sections */
.detail-price-section {
  background: var(--m-card);
  border: 1px solid var(--m-hairline);
  border-radius: var(--radius-lg);
  padding: var(--sp-4);
  margin-bottom: var(--sp-3);
  box-shadow: 0 1px 3px var(--m-shadow);
}
.detail-price-header {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: var(--sp-3);
}
.detail-specs-header {
  margin-bottom: var(--sp-2);
}
.detail-price-icon {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius);
  flex: 0 0 auto;
}
.detail-price-icon--store {
  background: var(--m-save-bg);
  color: var(--m-save-ink);
}
.detail-price-icon--online {
  background: var(--m-online-bg);
  color: var(--m-online-ink);
}
.detail-price-label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--m-ink-2);
}
.detail-specs-title {
  font-size: 0.95rem;
}
.detail-price-row {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
  margin-bottom: var(--sp-2);
}
.detail-price-main {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--m-price);
  line-height: 1;
}
.detail-price-main.is-blue {
  color: var(--m-zhe-ink);
}
.detail-price-orig {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 0.95rem;
  color: var(--m-muted);
  text-decoration: line-through;
}
.detail-price-badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin-bottom: var(--sp-2);
}
.badge {
  display: inline-flex;
  align-items: center;
  font-family: var(--font-sans);
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.5;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  white-space: nowrap;
}
.badge--save {
  background: var(--m-save-bg);
  color: var(--m-save-ink);
}
.badge--date {
  background: var(--m-date-bg);
  color: var(--m-date-ink);
}
.badge--zhe {
  background: var(--m-zhe-bg);
  color: var(--m-zhe-ink);
}
.badge--online-only {
  background: var(--m-online-bg);
  color: var(--m-online-ink);
}
.detail-online-badge {
  margin-left: auto;
}
.detail-price-note {
  font-size: 0.75rem;
  color: var(--m-muted);
  margin: 0;
  line-height: 1.4;
}
.detail-price-verify {
  font-size: 0.75rem;
  color: var(--m-muted);
  cursor: pointer;
  text-decoration: underline;
  text-decoration-color: var(--m-hairline);
  background: none;
  border: none;
  padding: var(--sp-1);
  font-family: var(--font-sans);
  align-self: center;
}
.detail-price-verify:active {
  color: var(--m-ink-2);
}
.detail-price-verify:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}

/* 6. dashed divider */
.detail-divider {
  border: none;
  border-top: 1px dashed var(--m-hairline);
  margin: var(--sp-4) 0;
}

/* 7. 規格摘要 2-col grid */
.detail-specs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3) var(--sp-4);
  font-size: 0.85rem;
}
.detail-spec-label {
  color: var(--m-muted);
  font-size: 0.75rem;
  margin-bottom: 2px;
}
.detail-spec-value {
  font-weight: 600;
  color: var(--m-ink);
}
.detail-specs-note {
  margin-top: var(--sp-2);
}

/* 8. fixed bottom CTA bar */
.detail-cta {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 10;
  display: flex;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4);
  padding-bottom: max(var(--sp-3), env(safe-area-inset-bottom, 0px));
  background: var(--m-card);
  border-top: 1px solid var(--m-hairline);
}
.detail-cta-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 48px;
  padding: 0 var(--sp-4);
  border-radius: var(--radius-lg);
  font-family: var(--font-sans);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  border: none;
  text-decoration: none;
  color: var(--m-ink-2);
  background: var(--m-card);
  transition: transform 0.1s, filter 0.15s;
}
.detail-cta-btn:active {
  transform: scale(0.97);
}
.detail-cta-btn:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}
.detail-cta-btn--primary {
  background: var(--m-brand);
  color: var(--m-brand-ink);
  flex: 1.5;
}
.detail-cta-btn--primary:active {
  filter: brightness(1.08);
}
.detail-cta-btn--primary.is-active {
  background: var(--m-good);
  color: var(--m-brand-ink);
}
.detail-cta-btn--secondary {
  background: var(--m-card);
  color: var(--m-ink-2);
  border: 1px solid var(--m-hairline);
}
.detail-cta-btn--secondary:active {
  background: var(--m-soft);
}
</style>
