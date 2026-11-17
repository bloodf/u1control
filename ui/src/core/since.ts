import { ref, watch, type Ref } from 'vue';

/** When a condition last became true (ms), 0 while it is false. A banner keyed on it stays dismissed while the
 *  condition holds, through every poll, and comes back the next time it starts. */
export function since(cond: () => boolean): Ref<number> {
  const at = ref(0);
  watch(cond, on => { at.value = on ? Date.now() : 0; }, { immediate: true });
  return at;
}
