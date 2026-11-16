import * as bridge from '../core/bridge';
import { s } from './store';

// Pictures of list rows: only for rows on screen (one shared observer, so rows are asked in list order), a few
// requests at a time per list, dropped when that list changes. Each list has its own queue, so reloading the
// print files never drops the time-lapse covers still waiting, and the other way round.
export const THUMBS_AT_ONCE = 2;
interface Job { gen: number; args: Record<string, unknown>; done: (src: string) => void }
const waiting = new Map<Element, () => void>();
let observer: IntersectionObserver | null = null;

function onScreen(el: Element, start: () => void): () => void {
  if (typeof IntersectionObserver === 'undefined') { start(); return () => {}; }
  observer ??= new IntersectionObserver(entries => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      observer!.unobserve(e.target);
      const go = waiting.get(e.target);
      waiting.delete(e.target);
      go?.();
    }
  }, { rootMargin: '200px' });
  waiting.set(el, start);
  observer.observe(el);
  return () => { waiting.delete(el); observer?.unobserve(el); };
}

function pictureQueue(cmd: string) {
  let queue: Job[] = [];
  let running = 0;
  let listGen = 0;
  function pump(): void {
    while (running < THUMBS_AT_ONCE && queue.length) {
      const job = queue.shift()!;
      if (job.gen !== listGen) continue;
      running++;
      bridge.command(cmd, job.args, s.info?.generation)
        .then(src => { if (src && job.gen === listGen) job.done(src); }, () => {})
        .finally(() => { running--; pump(); });
    }
  }
  return {
    /** A new list: what was waiting for the old one is dropped. Returns the list's generation. */
    reset(): number { queue = []; return ++listGen; },
    /** Returns the row's way out: it stops waiting for the screen and leaves the queue (a row that is gone asks for nothing). */
    watch(el: Element, gen: number, args: Record<string, unknown>, done: (src: string) => void): () => void {
      const job = { gen, args, done };
      const unwatch = onScreen(el, () => { queue.push(job); pump(); });
      return () => { unwatch(); queue = queue.filter(j => j !== job); };
    },
  };
}

const thumbs = pictureQueue('thumbnail');
export const newFolder = thumbs.reset;
export const watchThumb = thumbs.watch;
/** Time-lapse covers (cmd_timelapse_cover). */
export const covers = pictureQueue('timelapse_cover');
