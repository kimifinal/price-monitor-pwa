<script setup>
// WatchlistEditor.vue — the #4 個人化 watchlist, DISPLAYED + EDITED offline.
//
// It never talks to a server: it reads a static seed / localStorage and writes
// back to localStorage (see lib/watchlist.js). Every change is persisted locally
// + emitted, so the PWA reflows the gate while offline.
//
// The verdict itself lives in monitor.js (priceVerdict / shouldAlert — the SSOT);
// this component only manages the GATE config.
import { ref, computed } from 'vue'
import {
  loadWatchlist,
  saveWatchlist,
  resetWatchlist,
  wouldAlert,
} from '../lib/watchlist.js'

const props = defineProps({
  // Seed the editor from a list instead of localStorage (used by tests / host).
  entries: { type: Array, default: null },
  // Optional probe: live metrics ({sku, price, dropPctFromHigh}) to preview
  // which watched items WOULD fire right now. Offline-optional.
  probe: { type: Array, default: null },
})

const emit = defineEmits(['change'])

// Ensure every entry has a threshold object so the inputs always bind cleanly.
function coerce(e) {
  if (!e || typeof e !== 'object') return null
  const base = { ...e, threshold: { ...(e.threshold || {}) } }
  if (base.sku == null) return null
  base.sku = String(base.sku)
  return base
}

const seed = props.entries ? (Array.isArray(props.entries) ? props.entries : []) : loadWatchlist()
const list = ref(seed.map(coerce).filter(Boolean))

// new-entry form fields
const newSku = ref('')
const newName = ref('')

const rows = computed(() => list.value)
const isEmpty = computed(() => rows.value.length === 0)

// A live "would fire?" preview, only when the host passes probe metrics.
function probeMatch(entry) {
  if (!Array.isArray(props.probe) || !props.probe) return null
  const hit = props.probe.find((p) => p && String(p.sku ?? '') === entry.sku)
  if (!hit) return null
  return wouldAlert(hit, [entry])
}

function persist() {
  saveWatchlist(rows.value)
  emit('change', rows.value.map((e) => ({ ...e })))
}

function onFieldChange() {
  persist()
}

function add() {
  const sku = newSku.value.trim()
  if (!sku) return
  list.value.push({ sku, name: newName.value.trim(), threshold: {} })
  newSku.value = ''
  newName.value = ''
  persist()
}

function remove(i) {
  list.value.splice(i, 1)
  persist()
}

function reset() {
  list.value = resetWatchlist().map(coerce)
  persist()
}
</script>

<template>
  <section class="watchlist-editor" data-testid="watchlist-editor">
    <div class="we-head">
      <h2>🎯 個人化追蹤（{{ rows.length }}）</h2>
      <button class="we-reset" type="button" data-testid="we-reset" @click="reset">
        恢復預設
      </button>
    </div>

    <p v-if="isEmpty" class="we-empty" data-testid="we-empty">
      清單為空 —— 不會有任何通知（沉默是預設）。
    </p>

    <ul class="we-list">
      <li
        v-for="(row, i) in rows"
        :key="row.sku || i"
        class="we-row"
        :data-testid="`we-row-${i}`"
      >
        <!-- top line: sku (mono) + name (flex, ellipsis) + remove, no overflow -->
        <div class="we-row-top">
          <span class="we-sku">{{ row.sku }}</span>
          <input
            class="we-name"
            v-model="row.name"
            placeholder="名稱（選填）"
            @change="onFieldChange"
          />
          <button class="we-remove" type="button" data-testid="we-remove" @click="remove(i)">
            移除
          </button>
        </div>

        <!-- threshold fields: label over input, 2-col when wide, stacks on phone -->
        <div class="we-th-fields">
          <label class="we-th">
            <span class="we-th-label">目標價</span>
            <input
              class="we-target"
              type="number"
              step="0.01"
              v-model.number="row.threshold.target"
              placeholder="目標(選填)"
              @change="onFieldChange"
            />
          </label>
          <label class="we-th">
            <span class="we-th-label">最低降幅%</span>
            <input
              class="we-drop"
              type="number"
              step="0.1"
              v-model.number="row.threshold.min_drop_pct"
              placeholder="最低降幅%"
              @change="onFieldChange"
            />
          </label>
        </div>

        <span
          v-if="probeMatch(row) !== null"
          class="we-fire"
          :data-fire="probeMatch(row)"
          >{{ probeMatch(row) ? '🔔 會觸發' : '待價' }}</span
        >
      </li>
    </ul>

    <form class="we-add" @submit.prevent="add">
      <input
        class="we-new-sku"
        v-model="newSku"
        placeholder="sku（如 3062725）"
        required
      />
      <input class="we-new-name" v-model="newName" placeholder="名稱（選填）" />
      <button class="we-add-btn" type="submit" data-testid="we-add-btn">
        新增
      </button>
    </form>
  </section>
</template>

<style scoped>
.watchlist-editor {
  background: #141218;
  border: 1px solid #2a2740;
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 16px;
}
.we-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.we-head h2 {
  font-size: 14px;
  color: #efeaff;
  margin: 0;
}
.we-reset,
.we-remove,
.we-add-btn {
  font-size: 12px;
  color: #b0a8c8;
  background: #1b1830;
  border: 1px solid #2a2740;
  border-radius: 6px;
  padding: 5px 10px;
  cursor: pointer;
  white-space: nowrap;
  flex: none;
}
.we-reset {
  background: #4a3f7a;
  color: #efeaff;
}
.we-empty {
  color: #8a86a8;
  font-size: 12px;
  margin: 4px 0 0;
}
.we-list {
  list-style: none;
  padding: 0;
  margin: 10px 0 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ---- one card per watched item ---- */
.we-row {
  background: #1b1830;
  border: 1px solid #2a2740;
  border-radius: 10px;
  padding: 10px;
}
.we-row-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.we-sku {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  color: #f0c000;
  white-space: nowrap;
  flex: none;
}
.we-name {
  flex: 1 1 auto;
  min-width: 0; /* allow flex to shrink so the value truncates with an ellipsis */
}
.we-remove {
  color: #e07a7a;
  border-color: #4a3345;
}

/* threshold fields: label stacked over each input; 2-col wide, 1-col narrow */
.we-th-fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}
@media (min-width: 380px) {
  .we-th-fields {
    flex-direction: row;
  }
}
.we-th {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.we-th-label {
  font-size: 11px;
  color: #8a86a8;
  white-space: nowrap;
}

.we-name,
.we-target,
.we-drop,
.we-new-sku,
.we-new-name {
  width: 100%;
  box-sizing: border-box;
  background: #141218;
  color: #efeaff;
  border: 1px solid #2a2740;
  border-radius: 6px;
  padding: 7px 8px;
  font-size: 13px;
}

.we-fire {
  display: inline-block;
  margin-top: 8px;
  font-size: 11px;
  color: #8a86a8;
}
.we-fire[data-fire='true'] {
  color: #4caf50;
  font-weight: bold;
}

/* add-form: stacked full-width on a phone, a row on wider screens */
.we-add {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
@media (min-width: 380px) {
  .we-add {
    flex-direction: row;
    align-items: center;
  }
}
.we-new-sku,
.we-new-name,
.we-add-btn {
  font-size: 13px;
}
.we-add-btn {
  background: #4a3f7a;
  color: #efeaff;
}
</style>
