<script setup>

const props = defineProps({
  item: { type: Object, required: true },
  alert: { type: Boolean, default: false },
})

const emit = defineEmits(['remove'])

// Import the alert decision from the single source of truth.
// NOTE: this component does NOT re-derive the rule; it only renders.
import { shouldAlert, alertMessage } from '../lib/monitor.js'

const isAlerting = () => shouldAlert(props.item)
const msg = () => alertMessage(props.item)

function remove() {
  emit('remove', props.item.id)
}
</script>

<template>
  <div class="item-card" :data-alert="isAlerting()">
    <div class="item-head">
      <h3>{{ item.name || '未命名' }}</h3>
      <button class="remove-btn" @click="remove">刪除</button>
    </div>
    <div class="item-price">
      <span class="price">${{ item.price?.toFixed(2) || '0.00' }}</span>
      <span class="target">/ 目標 ${{ item.target?.toFixed(2) }}</span>
    </div>
    <p class="msg" :class="{ hot: isAlerting() }">{{ msg() }}</p>
    <a v-if="item.url" :href="item.url" target="_blank" rel="noopener">查看 →</a>
  </div>
</template>

<style>
.item-card {
  background: #141218;
  border: 1px solid #2a2740;
  border-radius: 10px;
  padding: 10px;
  margin-bottom: 8px;
}
.item-card[data-alert='true'] {
  border-color: #4caf50;
  box-shadow: 0 0 0 1px #4caf50 inset;
}
.remove-btn {
  font-size: 12px;
  color: #b0a8c8;
}
.hot {
  color: #4caf50;
  font-weight: bold;
}
</style>
