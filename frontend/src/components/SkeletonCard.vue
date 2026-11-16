<script setup>
// SkeletonCard.vue — loading placeholders for the 即時比價 (live) section (#25).
//
// While the live snapshot loads, this draws N shimmering placeholder cards that
// mimic PriceHistory.vue's card SHAPE + FOOTPRINT (a head row with a title +
// badge placeholder, a sparkline placeholder, and a foot row). Because the
// placeholder occupies the same box the real card will, swapping skeleton →
// real causes NO layout shift. The shimmer keyframe and every colour live in
// src/style.css (the design-token SSOT, issue #21) — this component carries no
// colour of its own. The animation is a universal `*` animation, so #22's
// prefers-reduced-motion guard (animation-duration: 0.001ms) disables it.
//
// :count = how many placeholder cards to render while loading.
// defineProps is called (not assigned) because the template uses the auto-exposed
// `count` binding directly; no script-level read of the props object.
defineProps({
  count: { type: Number, default: 3 },
})
</script>

<template>
  <div class="skeleton">
    <div v-for="i in count" :key="i" class="skeleton-card">
      <div class="sk-head">
        <span class="sk-line sk-name"></span>
        <span class="sk-line sk-badge"></span>
      </div>
      <div class="sk-line sk-spark"></div>
      <div class="sk-foot">
        <span class="sk-line sk-now"></span>
        <span class="sk-line sk-pts"></span>
      </div>
    </div>
  </div>
</template>
