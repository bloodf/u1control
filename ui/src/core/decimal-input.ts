// PrimeVue's InputNumber reads only its locale's decimal sign: in de, es and pt-BR a typed or pasted "2.5" became 25.
// Spread on an InputNumber (v-bind), these capture listeners turn a '.' into the locale's sign before PrimeVue sees it,
// so both '.' and the locale's own sign work while the field keeps showing the locale's format.

/** The decimal sign Intl uses for `locale` (',' in de/es/pt-BR, '.' in en and zh-CN). */
export const decimalSign = (locale?: string): string =>
  new Intl.NumberFormat(locale).formatToParts(1.1).find(p => p.type === 'decimal')?.value ?? '.';

/** Type `text` into an InputNumber's field the way a keyboard does, through PrimeVue's own keypress handling. */
function retype(input: HTMLInputElement, text: string) {
  for (const key of text) input.dispatchEvent(new KeyboardEvent('keypress', { key, bubbles: true, cancelable: true }));
}

export function acceptDot(locale?: string) {
  const sign = decimalSign(locale);
  return {
    onKeypressCapture(e: KeyboardEvent) {
      if (sign === '.' || e.key !== '.' || !(e.target instanceof HTMLInputElement)) return;
      e.stopPropagation();
      e.preventDefault();
      retype(e.target, sign);
    },
    onPasteCapture(e: ClipboardEvent) {
      const text = e.clipboardData?.getData('text/plain').trim() ?? '';
      if (sign === '.' || !/^-?\d*\.\d+$/.test(text) || !(e.target instanceof HTMLInputElement)) return;
      e.stopPropagation();
      e.preventDefault();
      retype(e.target, text.replace('.', sign));
    },
  };
}
