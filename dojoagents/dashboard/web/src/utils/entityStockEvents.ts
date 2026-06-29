import type { EntityStockEventItem, StockEventRow } from '../types/entity';

function normalizeEventDate(raw: string | null | undefined): string {
  const text = String(raw ?? '').trim();
  if (!text) return '';
  if (text.includes('T')) return text.split('T', 1)[0] ?? text;
  if (text.includes(' ')) return text.split(' ', 1)[0] ?? text;
  return text.slice(0, 10);
}

function eventRowId(row: StockEventRow, index: number): string {
  for (const key of ['id', 'event_id', 'remind_id', 'reminder_id', 'notice_id'] as const) {
    const value = row[key as keyof StockEventRow];
    if (value != null && String(value).trim()) {
      return String(value).trim();
    }
  }
  const date = normalizeEventDate(
    row.notice_date ?? row.event_date ?? row.remind_date ?? null,
  );
  const typeLabel = resolveEventTypeLabel(row);
  const content = resolveEventContent(row);
  return `${date}|${typeLabel}|${content}|${index}`;
}

export function resolveEventTypeLabel(row: StockEventRow): string {
  for (const key of ['event_type', 'specific_eventtype', 'event_type_name', 'type_name', 'type'] as const) {
    const value = row[key as keyof StockEventRow];
    if (value != null && String(value).trim()) {
      return String(value).trim();
    }
  }
  return '';
}

export function resolveEventContent(row: StockEventRow): string {
  for (const key of ['content', 'event_content', 'level1_content', 'level2_content', 'title'] as const) {
    const value = row[key as keyof StockEventRow];
    if (value != null && String(value).trim()) {
      return String(value).trim();
    }
  }
  return '';
}

export function mapStockEventsToEntityItems(rows: StockEventRow[]): EntityStockEventItem[] {
  return rows
    .map((row, index) => ({
      id: eventRowId(row, index),
      date: normalizeEventDate(row.notice_date ?? row.event_date ?? row.remind_date),
      typeLabel: resolveEventTypeLabel(row),
      content: resolveEventContent(row),
    }))
    .sort((left, right) => {
      if (!left.date && !right.date) return 0;
      if (!left.date) return 1;
      if (!right.date) return -1;
      return right.date.localeCompare(left.date);
    });
}
