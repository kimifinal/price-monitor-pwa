<script setup>
import { ref, computed, onMounted } from 'vue'
import { loadItems, saveItems } from './lib/storage.js'
import { alertedItems, sortByUrgency } from './lib/monitor.js'
import { loadLiveHistory } from './lib/history.js'
import AddItemForm from './components/AddItemForm.vue'
import SectionIcon from './components/SectionIcon.vue'
import ItemCard from './components/ItemCard.vue'
import PriceHistory from './components/PriceHistory.vue'
import WatchlistEditor from './components/WatchlistEditor.vue'
// #25: loading-placeholders for the live section (no layout shift). Bound as
// <skeleton-cards> in the template below.
import SkeletonCards from './components/SkeletonCard.vue'
// MVM 檔期目錄 (offline-baked catalog). loadMvmCatalog reads the committed
// snapshot in src/data/mvm.json, so this section renders ALL 6 檔期 with no
// network — mirroring how loadLiveHistory keeps the 比價 cards offline-safe.
import MvmCatalog from './components/MvmCatalog.vue'
import { loadMvmCatalog } from './lib/mvm.js'
// issue #23: live-section collapse + 3-state filter. Pure helpers that REUSE the
// verdict SSOT (monitor.js) — never re-derive a verdict. FOLD_LIMIT is left out of
// this import: foldCards already applies it as its internal default, so importing
// it here would be an unused-var (kept exported from live-fold.js for the unit test).
import { filterLive, foldCards } from './lib/live-fold.js'

const items = ref(loadItems())

const alerts = computed(() => alertedItems(items.value))
const sorted = computed(() => sortByUrgency(items.value))

// --- MVM 檔期目錄（離線 baked，6 檔期） -----------------------------------
// Baked in src/data/mvm.json, so the WHOLE catalog renders offline with no
// fetch — mirroring how loadLiveHistory keeps the 比價 cards offline-safe. The
// default active tab is the first 檔期 carrying products (MvmCatalog picks it;
// an empty 檔期 never owns the first screen).
const mvm = loadMvmCatalog()
const mvmTabs = mvm.tabs
const mvmPriceTypes = mvm.priceTypes
const mvmSourceDate = mvm.sourceDate

// --- 歷史價格比價 demo -------------------------------------------------------
// An offline sample series (no backend needed in the PWA). In production this
// section fetches GET /api/costco/history and maps each item to this `card`
// shape, so the same component renders real data unchanged.
const compareCards = [
  {
    name: 'BOSE Solo Soundbar 電視音響 II',
    current: 8149,
    series: [10800, 10200, 9699, 9200, 8750, 8149],
    metrics: { points: 6, atAllTimeLow: true, dropPctFromHigh: 24.8 },
    url: 'https://www.costco.com.tw/p/3062725',
  },
  {
    name: 'Samsung 55吋 Mini LED 4K AI 量子智慧顯示器',
    current: 18999,
    series: [24200, 23100, 21500, 20400, 19800, 18999],
    metrics: { points: 6, atAllTimeLow: true, dropPctFromHigh: 21.5 },
    url: 'https://www.costco.com.tw/p/161520',
  },
  {
    name: 'ANKER 67W GaN 急速充電器 2入組',
    current: 1069,
    series: [1375, 1299, 1199, 1150, 1120, 1069],
    metrics: { points: 6, atAllTimeLow: true, dropPctFromHigh: 22.2 },
    url: 'https://www.costco.com.tw/p/149699',
  },
]
const compareRows = computed(() =>
  [...compareCards].sort(
    (a, b) => b.metrics.dropPctFromHigh - a.metrics.dropPctFromHigh,
  ),
)

// --- 即時比價（離線可用）— issue #6: real /api data, offline-first ----------------
// loadLiveHistory() tries the live API first (the service worker in src/sw.js
// serves the cache when online, else the committed snapshot), so these cards are
// driven by real last-known series + verdicts and render with NO network. It
// degrades to [] on total failure; it never throws, so the hard-coded samples
// above still stand as the offline fallback. Kept in its own section so the
// static 4-card compare demo (guarded by e2e) is untouched.
const liveCards = ref([])
// #25: true until the live (re)load settles. Drives the no-layout-shift skeleton
// in the live section: skeleton while loading, real cards when loaded, a subtitle
// only when truly empty (post-load, no data).
const loading = ref(true)
onMounted(async () => {
  try {
    const base = import.meta.env.BASE_URL || ''
    liveCards.value = await loadLiveHistory(base)
  } catch {
    liveCards.value = []
  } finally {
    loading.value = false
  }
})

// --- issue #23: live-section collapse + 3-state filter -----------------------
// Default filter is 'triggered' (issue's "only show the buy-now cards"), which
// on today's 52-card snapshot is 46 cards; fold them down to FOLD_LIMIT visible.
// The three chips: 全部 / 僅觸發 / 近低點 (近低點 ⊂ 僅觸發, design §5.1).
const FILTER_OPTS = [
  { k: 'all', label: '全部' },
  { k: 'triggered', label: '僅觸發' },
  { k: 'near-low', label: '近低點' },
]
const activeFilter = ref('triggered')
const expanded = ref(false)

// Filter first, then fold the result.
const filtered = computed(() => filterLive(liveCards.value, activeFilter.value))
// empty-fallback: a filter that matches 0 cards still renders the full set, so the
// section never empties — this is what keeps the offline e2e "≥1 movement card"
// guard green even when a chip (e.g. 近低點 on a 0-good_deal snapshot) matches none.
const shownSource = computed(() =>
  filtered.value.length ? filtered.value : liveCards.value,
)
// Only the visible slice is mounted; the rest live behind the expand toggle.
const fold = computed(() => foldCards(shownSource.value, { expanded: expanded.value }))

function persist() {
  saveItems(items.value)
}

function onAdd(item) {
  items.value.push(item)
  persist()
}

function onRemove(id) {
  items.value = items.value.filter((i) => i.id !== id)
  persist()
}

// The watchlist editor self-persists to localStorage (offline). The parent keeps
// a reference to the latest gate so it could, e.g., re-run wouldAlert() against
// live prices; the gate itself lives in the editor + lib/watchlist.js.
function onWatchlistChange(wl) {
  return wl
}
</script>

<template>
  <div class="app">
    <header class="app-header">
      <h1>Price Monitor</h1>
      <p class="subtitle">追蹤目標價，跌破就通知你</p>
    </header>

    <section class="alerts" v-if="alerts.length">
      <h2><section-icon name="bell" title="已觸發通知" /> 已觸發 {{ alerts.length }} 筆</h2>
      <item-card
        v-for="item in alerts"
        :key="item.id"
        :item="item"
        @remove="onRemove"
      />
    </section>

    <section class="watchlist">
      <h2><section-icon name="target" title="手動追蹤清單" /> 手動追蹤（{{ items.length }}）</h2>
      <p class="subtitle">手動加入的名單，依緊迫度排序，目標價跌破現價就通知。</p>
      <add-item-form @add="onAdd" />
      <item-card
        v-for="item in sorted"
        :key="item.id"
        :item="item"
        @remove="onRemove"
      />
    </section>

    <section class="personalize">
      <h2><section-icon name="gear" title="自動門檻" /> 自動門檻 Gate（離線可編輯）</h2>
      <p class="subtitle">
        每項的「觸發開關」，只有清單內、且達到目標價 / 最低降幅門檻的品項才會通知；清單為空則永遠沉默。
      </p>
      <watchlist-editor @change="onWatchlistChange" />
    </section>

    <section class="price-history" data-section="compare">
      <h2><section-icon name="chart" title="歷史價格比價" /> 歷史價格比價 · 3C / 家電</h2>
      <p class="subtitle">依近期降幅排序，綠色 = 歷史最低、可考慮入手</p>
      <price-history
        v-for="card in compareRows"
        :key="card.name"
        :card="card"
      />
    </section>

    <section class="price-history" data-section="live">
      <h2><section-icon name="signal" title="即時比價" /> 即時比價（離線可用）</h2>
      <p class="subtitle">
        由離線快取 / 快照驅動，無網路時仍渲染最新走勢與結論（離線 PWA · #6）
      </p>
      <!-- #23: collapse + 3-state filter. skeleton while loading (no layout shift,
           #25), folded cards when loaded, a "no data" subtitle only when truly empty. -->
      <template v-if="liveCards.length">
        <!-- 篩選 toggle：全部 / 僅觸發 / 近低點 (radiogroup，:focus-visible，4px grid，token 色) -->
        <div class="live-filter" role="group" aria-label="即時比價 篩選">
          <button
            v-for="opt in FILTER_OPTS"
            :key="opt.k"
            type="button"
            class="live-chip"
            :class="{ 'is-active': activeFilter === opt.k }"
            :aria-pressed="activeFilter === opt.k"
            @click="activeFilter = opt.k"
          >
            {{ opt.label }}
          </button>
        </div>
        <!-- fold：only render fold.visible; the rest live behind the expand toggle.
             aria-expanded tracks `expanded` (a11y), chevron via SectionIcon (no emoji,
             sloplint 30a). -->
        <price-history
          v-for="(card, i) in fold.visible"
          :key="`live-${i}`"
          :card="card"
        />
        <button
          v-if="fold.foldedCount > 0"
          type="button"
          class="live-fold"
          :aria-expanded="expanded"
          data-section="live-fold-toggle"
          @click="expanded = !expanded"
        >
          <section-icon :name="expanded ? 'chevron-up' : 'chevron-down'" title="展開/收起其餘" />
          <span>{{ expanded ? '收起其餘' : `展開其餘 ${fold.foldedCount}` }}</span>
        </button>
        <!-- empty-fallback note: a chip matched 0 cards, so we show the full set. -->
        <p v-if="!filtered.length" class="subtitle">
          此條件 0 筆，顯示全部 {{ liveCards.length }} 筆
        </p>
      </template>
      <skeleton-cards v-else-if="loading" :count="3" />
      <p v-else class="subtitle">尚無即時資料</p>
    </section>

    <!-- MVM 檔期目錄 (B4): the offline-baked 6-檔期 catalog. Self-styles; lazy
         grid renders only the active 檔期's cards. All 6 tabs are reachable. -->
    <section class="mvm" data-section="mvm">
      <MvmCatalog
        :tabs="mvmTabs"
        :price-types="mvmPriceTypes"
        :source-date="mvmSourceDate"
      />
    </section>
  </div>
</template>

<style>
.app {
  font-family: var(--font-sans);
  color: var(--text);
  background: var(--bg);
  max-width: 480px;
  margin: 0 auto;
  padding: 16px;
}
.alerts {
  background: var(--surface-1);
  border: 1px solid var(--accent);
  border-radius: var(--radius);
  padding: 12px;
  margin-bottom: 16px;
}

/* --- issue #23: live-section 3-state filter chips + "expand the rest" toggle.
 * Colours as var(--token) only (CI guards raw hex; gate 48); spacing on the 4px
 * token grid (gate 24b: every value >2px is a multiple of 4); the instant focus
 * ring via :focus-visible is global (style.css button:focus-visible) but restated
 * here so the chip/fold contract is explicit (gate 15: no focus transition;
 * gate 26a: a focus style is present). No emoji on the expand affordance
 * (gate 30a): it is a line-icon chevron through the SectionIcon SSOT. */
.live-filter {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin-bottom: var(--sp-3);
}
.live-chip {
  /* a control, not a card (gate 4). body face, sentence case (gate 67). */
  font-family: var(--font-sans);
  font-size: 0.82rem;
  line-height: 1.2;
  color: var(--text-2);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  padding: var(--sp-2) var(--sp-3);
  min-height: 44px;
  cursor: pointer;
  white-space: nowrap;
}
.live-chip:hover {
  border-color: var(--border-2);
}
.live-chip.is-active {
  border-color: var(--accent);
  background: var(--surface-1);
  color: var(--text);
}
.live-fold {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
  font-family: var(--font-sans);
  font-size: 0.82rem;
  color: var(--link);
  background: transparent;
  border: 1px solid var(--border-2);
  border-radius: var(--radius-pill);
  padding: var(--sp-2) var(--sp-3);
  min-height: 44px;
  cursor: pointer;
}
.live-fold:hover {
  border-color: var(--accent);
}
/* gate 26a/26b: explicit interactive states on the chip + fold controls. */
.live-chip:focus-visible,
.live-fold:focus-visible {
  outline: 2px solid var(--accent-hover);
  outline-offset: 2px;
}
.live-chip:active,
.live-fold:active {
  filter: brightness(1.12);
}
</style>
