<script setup>
import { ref, computed } from 'vue'
import { loadItems, saveItems } from './lib/storage.js'
import { alertedItems, sortByUrgency } from './lib/monitor.js'
import AddItemForm from './components/AddItemForm.vue'
import ItemCard from './components/ItemCard.vue'

const items = ref(loadItems())

const alerts = computed(() => alertedItems(items.value))
const sorted = computed(() => sortByUrgency(items.value))

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
