import type { EntityStockNewsItem, StockNewsRow } from '../types/entity';

/** Normalize publish dates to YYYY-MM-DD for DojoCore display. */
function normalizeNewsDate(raw: string | null | undefined): string {
  const text = String(raw ?? '').trim();
  if (!text) return '';
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  if (text.includes('T')) return text.split('T', 1)[0] ?? text;
  if (/^\d{4}-\d{2}-\d{2}/.test(text)) return text.slice(0, 10);

  const parsed = Date.parse(text);
  if (!Number.isNaN(parsed)) {
    const date = new Date(parsed);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  if (text.includes(' ')) {
    const head = text.split(' ', 1)[0] ?? text;
    if (/^\d{4}-\d{2}-\d{2}$/.test(head)) return head;
  }

  return text.slice(0, 10);
}

function newsRowId(row: StockNewsRow, index: number): string {
  if (row.id != null && String(row.id).trim()) {
    return String(row.id).trim();
  }
  const date = normalizeNewsDate(row.publish_date);
  const title = String(row.title ?? '').trim();
  return `${date}|${title}|${index}`;
}

export function mapStockNewsToEntityItems(rows: StockNewsRow[]): EntityStockNewsItem[] {
  return rows
    .map((row, index) => {
      const title = String(row.title ?? '').trim();
      const url = String(row.url ?? '').trim();
      if (!title) return null;
      return {
        id: newsRowId(row, index),
        date: normalizeNewsDate(row.publish_date),
        title,
        url,
      };
    })
    .filter((item): item is EntityStockNewsItem => item != null);
}
