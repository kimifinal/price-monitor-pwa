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
  serializeWatchlist,
  deserializeWatchlist,
  buildExportBlob,
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

// ---- #11: portable export/import (offline, no network) ----
const showExport = ref(false)
const showImport = ref(false)
const exportJson = ref('')
const importText = ref('')
const importMsg = ref('')

function doExport() {
  exportJson.value = serializeWatchlist(rows.value)
  showExport.value = true
  showImport.value = false
}

async function copyExport() {
  try {
    await navigator.clipboard.writeText(exportJson.value)
    importMsg.value = '已複製到剪貼簿。'
  } catch {
    importMsg.value = '無法複製，請手動選取。'
  }
}

function downloadExport() {
  const blob = buildExportBlob(rows.value)
  if (!blob) {
    importMsg.value = '瀏覽器不支援下載。'
    return
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'watchlist.json'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
  importMsg.value = '已下載 watchlist.json。'
}

function doImport() {
  const { entries, errors } = deserializeWatchlist(importText.value)
  if (errors.length) {
    importMsg.value = `匯入跳過 ${errors.length} 筆：${errors
      .map((e) => `${e.sku ?? '?'}` ? `${e.sku}: ${e.error}` : e.error)
      .join('；')}`
  }
  // merge: last-wins dedup
  const map = new Map(list.value.map((e) => [e.sku, e]))
  for (const e of entries) {
    map.set(e.sku, { ...e, threshold: e.threshold ? { ...e.threshold } : {} })
  }
  list.value = [...map.values()]
  importText.value = ''
  showImport.value = false
  persist()
}
</script>

<template>
  <section class="watchlist-editor" data-testid="watchlist-editor">
    <div class="we-head">
      <h2>🎯 個人化追蹤（{{ rows.length }}）</h2>
      <div class="we-head-actions">
        <button class="we-export" type="button" data-testid="we-export" @click="doExport">
          匯出
        </button>
        <button class="we-import" type="button" data-testid="we-import-toggle" @click="showImport = !showImport; showExport = false">
          匯入
        </button>
        <button class="we-reset" type="button" data-testid="we-reset" @click="reset">
          恢復預設
        </button>
      </div>
    </div>

    <!-- Export panel -->
    <div v-if="showExport" class="we-io-panel" data-testid="we-export-panel">
      <p class="we-io-hint" data-testid="we-export-hint">
        複製後端 JSON 給其他裝置或備份用：
      </p>
      <textarea
        class="we-export-json"
        :value="exportJson"
        rows="6"
        readonly
        data-testid="we-export-raw"
      ></textarea>
      <div class="we-io-actions">
        <button class="we-copy" type="button" data-testid="we-copy" @click="copyExport">
          複製到剪貼簿
        </button>
        <button class="we-download" type="button" data-testid="we-download" @click="downloadExport">
          下載 JSON
        </button>
      </div>
    </div>

    <!-- Import panel -->
    <div v-if="showImport" class="we-io-panel" data-testid="we-import-panel">
      <p class="we-io-hint">貼上匯出的 JSON：</p>
      <textarea
        v-model="importText"
        class="we-import-json"
        rows="6"
        placeholder='"[ ... ]"'
        data-testid="we-import-raw"
      ></textarea>
      <div class="we-io-actions">
        <button class="we-do-import" type="button" data-testid="we-do-import" @click="doImport">
          確認匯入
        </button>
        <span v-if="importMsg" class="we-import-msg" :data-testid="`we-import-msg`">
          {{ importMsg }}
        </span>
      </div>
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
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
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
  color: var(--text);
  margin: 0;
}
.we-reset,
.we-remove,
.we-add-btn {
  font-size: 12px;
  color: var(--text-2);
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 10px;
  cursor: pointer;
  white-space: nowrap;
  flex: none;
}
.we-reset {
  background: var(--accent);
  color: var(--text);
}
.we-empty {
  color: var(--text-3);
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
  background: var(--surface-1);
  border: 1px solid var(--border);
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
  color: var(--sku);
  white-space: nowrap;
  flex: none;
}
.we-name {
  flex: 1 1 auto;
  min-width: 0; /* allow flex to shrink so the value truncates with an ellipsis */
}
.we-remove {
  color: var(--danger);
  border-color: var(--danger-b);
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
  color: var(--text-3);
  white-space: nowrap;
}

.we-name,
.we-target,
.we-drop,
.we-new-sku,
.we-new-name {
  width: 100%;
  box-sizing: border-box;
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px 8px;
  font-size: 13px;
}

.we-fire {
  display: inline-block;
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-3);
}
.we-fire[data-fire='true'] {
  color: var(--success);
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
  background: var(--accent);
  color: var(--text);
}

/* ---- #11: export / import ---- */
.we-head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.we-export,
.we-import {
  font-size: 12px;
  color: var(--text-2);
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 10px;
  cursor: pointer;
  white-space: nowrap;
}
.we-export {
  background: var(--export-bg);
  border-color: var(--export-border);
  color: var(--success-tx);
}
.we-import {
  background: var(--import-bg);
  border-color: var(--import-border);
  color: var(--import-text);
}
.we-io-panel {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px;
  margin: 10px 0 0 0;
  background: var(--surface-2);
}
.we-io-hint {
  margin: 0 0 8px 0;
  font-size: 12px;
  color: var(--text-3);
}
.we-export-json,
.we-import-json {
  width: 100%;
  box-sizing: border-box;
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  resize: vertical;
  min-height: 80px;
}
.we-io-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 8px;
}
.we-copy,
.we-download,
.we-do-import {
  font-size: 12px;
  color: var(--text);
  background: var(--accent);
  border: 1px solid var(--border-2);
  border-radius: 6px;
  padding: 5px 12px;
  cursor: pointer;
}
.we-import-msg {
  font-size: 11px;
  color: var(--success-tx);
}
</style>
