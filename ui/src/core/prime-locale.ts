// PrimeVue's own labels (empty lists, dialog close…) for the languages the shared foundation does not carry yet
// (ui/shared 4.0.1 has English and pt-BR). No calendar names: the pages have no date picker.
import type { PrimeVueConfiguration } from 'primevue/config';
import { primeVueOptions } from '../../shared/src';
import type { Locale } from './i18n-core';

type PrimeLocale = NonNullable<PrimeVueConfiguration['locale']>;

const OWN: Partial<Record<Locale, Partial<PrimeLocale>>> = {
  es: {
    accept: 'Confirmar', reject: 'Volver', choose: 'Seleccionar', upload: 'Subir', cancel: 'Cancelar',
    emptyMessage: 'No hay elementos', emptyFilterMessage: 'Ningún resultado con estos filtros',
    emptySearchMessage: 'No se encontraron resultados', searchMessage: '{0} resultados encontrados',
    selectionMessage: '{0} elementos seleccionados', emptySelectionMessage: 'Ningún elemento seleccionado',
    aria: { close: 'Cerrar', previous: 'Anterior', next: 'Siguiente', firstPageLabel: 'Primera página', lastPageLabel: 'Última página',
      nextPageLabel: 'Página siguiente', prevPageLabel: 'Página anterior', selectRow: 'Seleccionar fila', unselectRow: 'Deseleccionar fila' },
  },
  de: {
    accept: 'Bestätigen', reject: 'Zurück', choose: 'Auswählen', upload: 'Hochladen', cancel: 'Abbrechen',
    emptyMessage: 'Keine Einträge', emptyFilterMessage: 'Keine Ergebnisse für diese Filter',
    emptySearchMessage: 'Keine Ergebnisse gefunden', searchMessage: '{0} Ergebnisse gefunden',
    selectionMessage: '{0} Einträge ausgewählt', emptySelectionMessage: 'Kein Eintrag ausgewählt',
    aria: { close: 'Schließen', previous: 'Zurück', next: 'Weiter', firstPageLabel: 'Erste Seite', lastPageLabel: 'Letzte Seite',
      nextPageLabel: 'Nächste Seite', prevPageLabel: 'Vorherige Seite', selectRow: 'Zeile auswählen', unselectRow: 'Zeilenauswahl aufheben' },
  },
  'zh-CN': {
    accept: '确定', reject: '返回', choose: '选择', upload: '上传', cancel: '取消',
    emptyMessage: '没有项目', emptyFilterMessage: '没有符合这些筛选条件的结果',
    emptySearchMessage: '未找到结果', searchMessage: '找到 {0} 个结果',
    selectionMessage: '已选择 {0} 项', emptySelectionMessage: '未选择任何项目',
    aria: { close: '关闭', previous: '上一个', next: '下一个', firstPageLabel: '第一页', lastPageLabel: '最后一页',
      nextPageLabel: '下一页', prevPageLabel: '上一页', selectRow: '选择行', unselectRow: '取消选择行' },
  },
};

/** The labels PrimeVue should use for a page language; undefined keeps its built-in English. */
export function primeLocale(locale: Locale): Partial<PrimeLocale> | undefined {
  return OWN[locale] ?? primeVueOptions(locale === 'pt-BR' ? 'pt-BR' : 'en').locale;
}
