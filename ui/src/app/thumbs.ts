import * as bridge from '../core/bridge';
import { s } from './store';

// Thumbnails: only for rows on screen (one shared observer, so rows are asked in list order), a few requests at
// a time, dropped when the folder changes.
export const THUMBS_AT_ONCE = 2;
interface Job { gen: number; args: Record<string, unknown>; done: (src: string) => void }
let queue: Job[] = [];
let running = 0;
let folderGen = 0;
const waiting = new Map<Element, () => void>();
let observer: IntersectionObserver | null = null;

export function newFolder(): number { queue = []; return ++folderGen; }
function pump(): void {
  while (running < THUMBS_AT_ONCE && queue.length) {
    const job = queue.shift()!;
    if (job.gen !== folderGen) continue;
    running++;
    bridge.command('thumbnail', job.args, s.info?.generation)
      .then(src => { if (src && job.gen === folderGen) job.done(src); }, () => {})
      .finally(() => { running--; pump(); });
  }
}
function want(job: Job): void { queue.push(job); pump(); }

export function watchThumb(el: Element, gen: number, args: Record<string, unknown>, done: (src: string) => void): () => void {
  const job = { gen, args, done };
  if (typeof IntersectionObserver === 'undefined') { want(job); return () => {}; }
  observer ??= new IntersectionObserver(entries => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      observer!.unobserve(e.target);
      const start = waiting.get(e.target);
      waiting.delete(e.target);
      start?.();
    }
  }, { rootMargin: '200px' });
  waiting.set(el, () => want(job));
  observer.observe(el);
  return () => { waiting.delete(el); observer?.unobserve(el); };
}
