import { onBeforeUnmount, onMounted } from 'vue';

/** Tell `set` whether an element is in the viewport (a hidden tab or a scrolled-away card is not), from mount to
 *  unmount; true again when it goes, so nothing is left held back. Without IntersectionObserver it always is. */
export function watchInView(el: () => Element | null | undefined, set: (inView: boolean) => void): void {
  let io: IntersectionObserver | undefined;
  onMounted(() => {
    const target = el();
    if (!target || typeof IntersectionObserver === 'undefined') return;
    io = new IntersectionObserver(entries => set(entries[entries.length - 1].isIntersecting));
    io.observe(target);
  });
  onBeforeUnmount(() => { io?.disconnect(); set(true); });
}
