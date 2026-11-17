<script setup>
// Icon.vue — the single source of truth for the app's icon vocabulary. #40.
//
// It replaces the colour emoji that sloplint (gates 19 / 30a) flags in section
// headers + the PriceHistory badges with restrained 16px monochrome LINE icons.
// stroke = currentColor, so an icon inherits whatever colour its heading / badge
// already paints (a good-deal verdict tints its icon automatically) — no second
// icon language, no per-use hard-coded colour, no emoji.
//
// One `name` -> one `d` (a single <path> whose subpaths carry shapes), so a new
// header picks a name from PATHS instead of re-drawing an emoji. Adding a glyph
// is one entry here; that keeps the vocabulary single-source and the 30a guard
// green by construction.
import { computed } from 'vue'

const props = defineProps({
  name: { type: String, required: true },
  // a11y: spoken label for the icon (headings already carry the text, so this is
  // decorative; pass '' to hide it from AT).
  title: { type: String, default: '' },
})

// Stroke-only geometry on a 24x24 grid. Circles are full-arc subpaths
// (`a r r 0 1 0 …`) so each icon stays a single <path> (no v-html, no extra els).
const PATHS = {
  bell: 'M6 8a6 6 0 0 1 12 0c0 5.5 2.5 7.5 3.5 8.5H2.5C3.5 15.5 6 13.5 6 8Z M9.5 20a2.5 2.5 0 0 0 5 0',
  target: 'M12 3a9 9 0 1 0 0 18 9 9 0 1 0 0-18 M12 7a5 5 0 1 0 0 10 5 5 0 1 0 0-10 M12 10.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 1 0 0-3',
  gear: 'M12 9a3 3 0 1 0 0 6 3 3 0 1 0 0-6 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5.2 5.2l2.1 2.1 M16.7 16.7l2.1 2.1 M16.7 7.3l2.1-2.1 M5.2 18.8l2.1-2.1',
  chart: 'M4 5v14h16 M8 14v5 M13 10v9 M18 6v13',
  signal: 'M5 12a7 7 0 0 1 7-7 M5 16a11 11 0 0 1 11-11 M6.5 13h.01 M12 18.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 1 0 0-3',
  cart: 'M3 4h2.2l1.9 9.5a1.5 1.5 0 0 0 1.5 1.2h8.4a1.5 1.5 0 0 0 1.5-1.2L20 7 M9.5 18a1.5 1.5 0 1 0 0 3 1.5 1.5 0 1 0 0-3 M17.5 18a1.5 1.5 0 1 0 0 3 1.5 1.5 0 1 0 0-3',
}

const d = computed(() => PATHS[props.name] || PATHS.bell)
</script>

<template>
  <svg
    class="icon"
    :class="`icon--${name}`"
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.75"
    stroke-linecap="round"
    stroke-linejoin="round"
    role="img"
    :aria-label="title"
    aria-hidden="false"
  >
    <path :d="d" />
  </svg>
</template>

<style>
.icon {
  display: inline-block;
  vertical-align: middle;
  flex: 0 0 auto;
}
</style>
