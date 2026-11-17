<script setup lang="ts">
// A U1 toolhead, drawn for U1 Control (an original illustration, not a photo): the dark head with its tube on top,
// the front plate with the head number, and the filament strand coming out of the nozzle in the mapped spool's colour.
defineProps<{ n: number; strand?: string | null }>();
</script>

<template>
  <svg class="hp" viewBox="0 0 80 120" aria-hidden="true">
    <path class="hp-tube" d="M40 2v14" />
    <rect class="hp-cap" x="31" y="12" width="18" height="10" rx="3" />
    <rect class="hp-body" x="16" y="20" width="48" height="58" rx="8" />
    <rect class="hp-plate" x="23" y="28" width="34" height="30" rx="4" />
    <circle class="hp-fan" cx="40" cy="43" r="9" />
    <circle class="hp-hub" cx="40" cy="43" r="2.5" />
    <rect class="hp-band" x="16" y="62" width="48" height="10" />
    <text class="hp-num" x="40" y="70" text-anchor="middle">{{ n }}</text>
    <path class="hp-nozzle" d="M33 78h14l-4 9h-6z" />
    <path class="hp-strand" :data-empty="strand ? undefined : true" :style="strand ? { stroke: strand } : undefined" d="M40 88v28" />
  </svg>
</template>

<style>
.hp { display: block; width: 72px; height: 108px; }
.hp-tube { stroke: color-mix(in srgb, var(--oui-text) 35%, transparent); stroke-width: 3; stroke-linecap: round; fill: none; }
.hp-cap { fill: #3a3a40; }
.hp-body { fill: #24242a; stroke: #45454d; stroke-width: 1.5; }
.hp-plate { fill: #303037; }
.hp-fan { fill: none; stroke: #6b6b75; stroke-width: 2; }
.hp-hub { fill: #6b6b75; }
.hp-band { fill: #f2c94c; }
.hp-num { font: 700 8px var(--oui-font); fill: #24242a; }
.hp-nozzle { fill: #b9bbc3; }
.hp-strand { stroke-width: 3; stroke-linecap: round; fill: none; }
.hp-strand[data-empty] { stroke: var(--oui-border); stroke-dasharray: 2 4; }
</style>
