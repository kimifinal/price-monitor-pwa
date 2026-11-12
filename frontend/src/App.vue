<script setup>
import { ref, computed, onMounted } from 'vue'
import { loadItems, saveItems } from './lib/storage.js'
import { alertedItems, sortByUrgency } from './lib/monitor.js'
import { loadLiveHistory } from './lib/history.js'
import AddItemForm from './components/AddItemForm.vue'
import ItemCard from './components/ItemCard.vue'
import PriceHistory from './components/PriceHistory.vue'
import WatchlistEditor from './components/WatchlistEditor.vue'

const items = ref(loadItems())

const alerts = computed(() => alertedItems(items.value))
const sorted = computed(() => sortByUrgency(items.value))

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
onMounted(async () => {
  try {
    const base = import.meta.env.BASE_URL || ''
    liveCards.value = await loadLiveHistory(base)
  } catch {
    liveCards.value = []
  }
})

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
      <h2>🔔 已觸發 {{ alerts.length }} 筆</h2>
      <item-card
        v-for="item in alerts"
        :key="item.id"
        :item="item"
        @remove="onRemove"
      />
    </section>

    <section class="watchlist">
      <h2>追蹤中（{{ items.length }}）</h2>
      <add-item-form @add="onAdd" />
      <item-card
        v-for="item in sorted"
        :key="item.id"
        :item="item"
        @remove="onRemove"
      />
    </section>

    <section class="personalize">
      <h2>🎯 個人化追蹤清單（離線可編輯）</h2>
      <p class="subtitle">
        只有清單內、且達到門檻的品項才會通知；清單為空時永遠沉默。
      </p>
      <watchlist-editor @change="onWatchlistChange" />
    </section>

    <section class="price-history" data-section="compare">
      <h2>📊 歷史價格比價 · 3C / 家電</h2>
      <p class="subtitle">依近期降幅排序，綠色 = 歷史最低、可考慮入手</p>
      <price-history
        v-for="card in compareRows"
        :key="card.name"
        :card="card"
      />
    </section>

    <section class="price-history" data-section="live">
      <h2>📡 即時比價（離線可用）</h2>
      <p class="subtitle">
        由離線快取 / 快照驅動 — 無網路時仍渲染最新走勢與結論（離線 PWA · #6）
      </p>
      <price-history
        v-for="(card, i) in liveCards"
        :key="`live-${i}`"
        :card="card"
      />
      <p v-if="!liveCards.length" class="subtitle">正在載入離線快照…</p>
    </section>
  </div>
</template>

<style>
.app {
  font-family: system-ui, -apple-system, sans-serif;
  color: #efeaff;
  background: #0f0d13;
  max-width: 480px;
  margin: 0 auto;
  padding: 16px;
}
.alerts {
  background: #1b1830;
  border: 1px solid #4a3f7a;
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 16px;
}
</style>
