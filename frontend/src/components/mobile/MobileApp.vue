<script setup>
// MobileApp.vue — the 暖色 e-commerce mobile app shell (案 B / #49), 品牌「好市多雷達」.
//
// A full-viewport warm shell with a 5-tab 底部導航: 首頁 / 特價 / 追蹤 / 全部 / 我的.
// The 特價 tab renders the warm MVM 檔期 view (MvmMobileCatalog — this pass's
// deliverable); 首頁 / 追蹤 / 全部 / 我的 are honest placeholders for a later
// pass (案 B ships the 特價 view). 特價 opens by default so the shipped view is
// on screen. Colours resolve only through the warm token scope var(--m-*)
// (declared on .mobile-app in style.css) — no raw hex (sloplint gate 48 / the CI
// css-token guard). Icons are MobileIcon line-icons (gate 30a/33: no emoji).
import { ref, computed } from 'vue'
import MobileIcon from './MobileIcon.vue'
import MvmMobileCatalog from './MvmMobileCatalog.vue'
import NewArrivalsMobile from './NewArrivalsMobile.vue'
import CatalogMobile from './CatalogMobile.vue'
import ProductDetail from './ProductDetail.vue'
import { loadMvmCatalog } from '../../lib/mvm.js'
import { loadCatalog } from '../../lib/catalog.js'
// #55 特價紀錄: the sku's costco-history record for the detail's 賣場 row.
// #56 線上序列: the MVM online series for the detail's 線上 row (null when the
// sku has no 檔期 → the row keeps its "待補" placeholder, never a faked curve).
import { recordBySku, onlineRecordBySku } from '../../lib/history.js'

// 5-tab 底部導航. 特價 = the MVM 檔期 view; 全部 = the 全庫 catalog view; the
// rest are placeholders.
// #48: 分頁對調 — 移除 'home'（其「全部商品」語意已折入 'all'），在 'deal' 後
// 插入 'new'（新品，探索導向）。順序：特價 / 新品 / 追蹤 / 全部 / 我的。
const TABS = [
  { key: 'deal', label: '特價', icon: 'tag' },
  { key: 'new', label: '新品', icon: 'spark' },
  { key: 'watch', label: '追蹤', icon: 'heart' },
  { key: 'all', label: '全部', icon: 'grid' },
  { key: 'me', label: '我的', icon: 'user' },
]
const active = ref('deal')
// The product currently displayed in the detail view (#53).
const selectedProduct = ref(null)
// #55 特價紀錄: the sku's costco-history record for the detail's 賣場 row. null
// when offline or the sku has no history → the 賣場 row reads "尚無歷史".
const selectedHistory = ref(null)
// #56 線上序列: the sku's MVM online series for the detail's 線上 row. null when
// the sku has no 檔期 → the 線上 row keeps its "待補" placeholder.
const selectedOnline = ref(null)
// Where to return when clicking "完成" back in the detail view (default 'deal').
const previousTab = ref('deal')

// Offline-baked MVM 檔期 catalog (lib/mvm.js), rendered by the 特價 tab.
const mvm = loadMvmCatalog()

// Offline-baked 全庫 catalog (lib/catalog.js, 10,049 items), rendered by the
// 全部 tab (#50) — the 賣場/線上 sliding toggle + the whole catalog.
const catalog = loadCatalog()

const activeTabObj = computed(() => TABS.find((t) => t.key === active.value) || TABS[0])
const activeLabel = computed(() => activeTabObj.value.label)
const currentIcon = computed(() => activeTabObj.value.icon)

function selectTab(key) {
  active.value = key
}

// Open the detail view for an item (#53). Remembers the origin tab so back() returns there.
function openDetail(product) {
  if (!product) return
  if (active.value !== 'detail') {
    previousTab.value = active.value
  }
  selectedProduct.value = product
  // #55: pull the sku's costco-history record for the 特價紀錄 賣場 row (null when
  // offline / no history → the row reads "尚無歷史", never a crash).
  selectedHistory.value = recordBySku(product.sku)
  // #56: the sku's MVM online series for the 線上 row (null when no 檔期 →
  // "待補" placeholder, never a faked curve).
  selectedOnline.value = onlineRecordBySku(product.sku)
  active.value = 'detail'
}

// Return from detail view to the previous browse tab.
function closeDetail() {
  active.value = previousTab.value || 'deal'
}
</script>

<template>
  <div class="mobile-app" data-mobile-app>
    <!-- top bar: brand + search + a few chrome buttons (the mockup's header) -->
    <header class="m-appbar">
      <div class="m-brand" aria-label="好市多雷達">
        <span class="m-brand-avatar" aria-hidden="true">
          <MobileIcon name="tag" :size="20" />
        </span>
        <span class="m-brand-name">好市多雷達</span>
      </div>
      <div class="m-appbar-mid">
        <MobileIcon name="search" :size="18" />
        <input
          class="m-search"
          type="search"
          inputmode="search"
          aria-label="搜尋商品"
          placeholder="搜尋商品或…"
        />
        <button type="button" class="m-appbar-btn" aria-label="全部商品">
          <MobileIcon name="grid" :size="18" />
        </button>
        <button type="button" class="m-appbar-btn" aria-label="通知">
          <MobileIcon name="bell" :size="18" />
        </button>
        <button type="button" class="m-appbar-btn m-appbar-user" aria-label="我的">
          <MobileIcon name="user" :size="18" />
        </button>
      </div>
    </header>

    <main class="m-content">
      <!-- 商品詳情頁 (#53): active === 'detail' full overlay view -->
      <ProductDetail
        v-if="active === 'detail' && selectedProduct"
        :product="selectedProduct"
        :history-record="selectedHistory"
        :online-record="selectedOnline"
        @back="closeDetail"
      />
      <!-- 特價 tab: the warm MVM 檔期 view -->
      <MvmMobileCatalog
        v-else-if="active === 'deal'"
        :tabs="mvm.tabs"
        :price-types="mvm.priceTypes"
        :source-date="mvm.sourceDate"
        @navigate="openDetail"
      />
      <!-- 新品 tab (#48): 探索導向的新品 list (period + category filters). -->
      <NewArrivalsMobile v-else-if="active === 'new'" />
      <!-- 全部 tab: the warm 全庫 catalog view (#50) — 賣場/線上 toggle + 10,049 items -->
      <CatalogMobile v-else-if="active === 'all'" :catalog="catalog" @navigate="openDetail" />
      <!-- 追蹤 / 我的: honest placeholders -->
      <section
        v-else
        class="m-placeholder"
        :data-tab="active"
        :aria-label="activeLabel"
      >
        <div class="m-placeholder-ico"><MobileIcon :name="currentIcon" :size="32" /></div>
        <p class="m-placeholder-title">「{{ activeLabel }}」開發中</p>
        <p class="m-placeholder-sub">本功能為佔位，將陸續上線。</p>
      </section>
    </main>

    <!-- 5-tab 底部導航 -->
    <nav class="m-tabbar" aria-label="主要導航">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        type="button"
        class="m-tab"
        :class="{ 'is-active': active === tab.key }"
        :aria-current="active === tab.key ? 'page' : undefined"
        :aria-label="tab.label"
        @click="selectTab(tab.key)"
      >
        <MobileIcon :name="tab.icon" :size="22" />
        <span class="m-tab-label">{{ tab.label }}</span>
      </button>
    </nav>
  </div>
</template>

<style>
/* Colours resolve ONLY through the warm token scope var(--m-*) — declared on
 * .mobile-app in style.css. Spacing on the shared 4px grid; radius shared. */
.mobile-app {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: flex;
  flex-direction: column;
  background: var(--m-bg);
  color: var(--m-ink);
  font-family: var(--font-sans);
}

/* top bar */
.m-appbar {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3);
  background: var(--m-bg);
}
.m-brand {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  flex: 0 0 auto;
}
.m-brand-avatar {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius);
  background: var(--m-warm);
  color: var(--m-brand-ink);
  flex: 0 0 auto;
}
.m-brand-name {
  font-weight: 700;
  font-size: 0.9rem;
  color: var(--m-ink);
  white-space: nowrap;
}
.m-appbar-mid {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex: 1 1 auto;
  min-width: 0;
}
.m-search {
  flex: 1 1 auto;
  min-width: 0;
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--m-hairline);
  border-radius: var(--radius-pill);
  background: var(--m-card);
  color: var(--m-ink);
  font-size: 0.85rem;
  min-height: 44px;
}
.m-appbar-btn {
  flex: 0 0 auto;
  width: 44px;
  height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--m-ink-2);
  cursor: pointer;
}
.m-appbar-user {
  border-radius: var(--radius-pill);
  background: var(--m-ink);
  color: var(--m-brand-ink);
}
.m-appbar-btn:active {
  filter: brightness(1.15);
}
.m-appbar-btn:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}
.m-search:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}
.m-search:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* content scroll region */
.m-content {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: var(--sp-3);
  padding-bottom: var(--sp-8);
}

/* placeholder for 首頁 / 追蹤 / 全部 / 我的 */
.m-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  text-align: center;
  padding: var(--sp-8) var(--sp-4);
  min-height: 50%;
}
.m-placeholder-ico {
  width: 56px;
  height: 56px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-lg);
  background: var(--m-soft);
  color: var(--m-muted);
}
.m-placeholder-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--m-ink);
  margin: 0;
}
.m-placeholder-sub {
  font-size: 0.8rem;
  color: var(--m-muted);
  margin: 0;
}

/* 5-tab 底部導航 */
.m-tabbar {
  flex: 0 0 auto;
  display: flex;
  align-items: stretch;
  justify-content: space-around;
  background: var(--m-nav-bg);
  border-top: 1px solid var(--m-hairline);
  padding: var(--sp-2) var(--sp-1) calc(var(--sp-3) + env(safe-area-inset-bottom, 0px));
}
.m-tab {
  flex: 1 1 0;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 56px;
  border: none;
  background: transparent;
  color: var(--m-muted);
  cursor: pointer;
  font-family: var(--font-sans);
  transition: color 0.15s;
}
.m-tab.is-active {
  color: var(--m-brand);
}
.m-tab-label {
  font-size: 0.68rem;
  line-height: 1.1;
}
.m-tab:active {
  transform: scale(0.96);
}
.m-tab:focus-visible {
  outline: 2px solid var(--m-brand);
  outline-offset: 2px;
}
</style>
