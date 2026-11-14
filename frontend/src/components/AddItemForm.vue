<script setup>
import { ref } from 'vue'

const emit = defineEmits(['add'])

const name = ref('')
const target = ref('')
const url = ref('')

function submit() {
  const targetNum = parseFloat(target.value)
  if (!name.value.trim() || !Number.isFinite(targetNum)) return
  const item = {
    id: `item-${Date.now()}`,
    name: name.value.trim(),
    target: targetNum,
    price: targetNum, // start at "unknown => at target"; backend overwrites on first fetch
    url: url.value.trim() || undefined,
    currency: 'TWD',
    createdAt: Date.now(),
  }
  emit('add', item)
  name.value = ''
  target.value = ''
  url.value = ''
}
</script>

<template>
  <form class="add-form" @submit.prevent="submit">
    <input v-model="name" placeholder="品名（如 Chiikawa 徽章）" required />
    <input
      v-model="target"
      type="number"
      step="0.01"
      placeholder="目標價"
      required
    />
    <input v-model="url" placeholder="品項連結（選填）" />
    <button type="submit">加入追蹤</button>
  </form>
</template>

<style>
.add-form {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.add-form input,
.add-form button {
  background: var(--surface-1);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px;
}
.add-form button {
  background: var(--accent);
  cursor: pointer;
}
</style>
