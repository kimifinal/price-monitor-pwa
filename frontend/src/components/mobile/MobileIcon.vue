<script setup>
// MobileIcon.vue — the warm mobile shell's LINE-icon vocabulary (#49 案 B).
//
// Self-contained (a separate file, NOT the dark SectionIcon SSOT which #40 owns),
// so the mobile shell can ship its own glyphs (home / tag / heart / grid / user /
// funnel / search / bell / box) without touching a dark component. Same contract
// as SectionIcon: stroke = currentColor so an icon inherits the colour its parent
// already paints (the nav tab tints var(--m-brand) when active, the heart fills
// var(--m-price) when wished), a single <path> per glyph (no emoji — gate 30a),
// and role="img"/aria-label (or aria-hidden when decorative) so gate 33 stays
// green. A new glyph is one PATHS entry.
import { computed } from 'vue'

const props = defineProps({
  name: { type: String, required: true },
  // spoken label; '' (default) makes the icon decorative (aria-hidden)
  title: { type: String, default: '' },
  size: { type: [Number, String], default: 22 },
})

// 24x24 stroke-only geometry (single <path>; multi-shape glyphs use M subpaths).
const PATHS = {
  home: 'M3 10.5 12 3l9 7.5 M5 9.4V21h14V9.4 M9.5 21v-6h5v6',
  tag: 'M20.59 13.41 13.42 20.58a2 2 0 0 1-2.83 0L3 13V3h10l7.59 7.59a2 2 0 0 1 0 2.83Z M7.5 7.5h.01',
  heart:
    'M12 20s-7-4.55-7-9.8A4.2 4.2 0 0 1 12 7a4.2 4.2 0 0 1 7 3.2C19 15.45 12 20 12 20Z',
  grid: 'M4 4h6.5v6.5H4Z M13.5 4H20v6.5h-6.5Z M4 13.5h6.5V20H4Z M13.5 13.5H20V20h-6.5Z',
  user: 'M12 4a3.5 3.5 0 1 0 0 7 3.5 3.5 0 1 0 0-7 M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6',
  funnel: 'M3.5 5h17 M6 9.5h12 M9.5 14h5 M5 18.5h14 M8.5 18.5 10 14h4l1.5 4.5',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 1 0 0-14 M20.5 20.5 16.3 16.3',
  bell: 'M6 8a6 6 0 0 1 12 0c0 5.5 2.5 7.5 3.5 8.5H2.5C3.5 15.5 6 13.5 6 8Z M9.5 20a2.5 2.5 0 0 0 5 0',
  box: 'M12 3 4 7v10l8 4 8-4V7z M4 7l8 4 8-4 M12 11v10',
}

const d = computed(() => PATHS[props.name] || PATHS.tag)
const deco = computed(() => props.title === '' || props.title == null)
</script>

<template>
  <svg
    class="m-ico"
    :class="`m-ico--${name}`"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.75"
    stroke-linecap="round"
    stroke-linejoin="round"
    role="img"
    :aria-label="props.title || undefined"
    :aria-hidden="deco ? 'true' : undefined"
  >
    <path :d="d" />
  </svg>
</template>

<style>
/* The icons ride the shared token SSOT's spacing; colour is inherited via
 * currentColor (the parent sets var(--m-*) / var(--m-brand)), so no hex here. */
.m-ico {
  display: inline-block;
  vertical-align: middle;
  flex: 0 0 auto;
}
</style>
