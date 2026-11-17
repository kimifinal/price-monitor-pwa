<script setup>

const props = defineProps({
  item: { type: Object, required: true },
  alert: { type: Boolean, default: false },
})

const emit = defineEmits(['remove'])

// Import the alert decision from the single source of truth.
// NOTE: this component does NOT re-derive the rule; it only renders.
import { shouldAlert, alertMessage } from '../lib/monitor.js'
// TWD 幣制展示 SSOT (issue #25): prices render via moneyTWD — no ".00", TWD prefix.
import { moneyTWD } from '../lib/format.js'

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
      <span class="price">{{ moneyTWD(item.price) }}</span>
      <span class="target">/ 目標 {{ moneyTWD(item.target) }}</span>
    </div>
    <p class="msg" :class="{ hot: isAlerting() }">{{ msg() }}</p>
    <a v-if="item.url" :href="item.url" target="_blank" rel="noopener" aria-label="開啟該商品產品網頁（新分頁）">查看</a>
  </div>
</template>

<style>
.item-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px;
  margin-bottom: 8px;
}
.item-card[data-alert='true'] {
  border-color: var(--success);
  box-shadow: 0 0 0 1px var(--success) inset;
}
.remove-btn {
  font-size: 12px;
  color: var(--text-2);
}
.item-card a:active,
.remove-btn:active { filter: brightness(1.2); }

.hot {
  color: var(--success);
  font-weight: bold;
}
</style>
