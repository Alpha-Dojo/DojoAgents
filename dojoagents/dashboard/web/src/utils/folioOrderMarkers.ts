import type { FolioOrder } from '../types/folio';
import type { MarketCode } from '../types/market';
import { findVisibleIndexForDate, indexToChartX } from './sectorPerformanceSeries';
import type { MarketSeriesPoint } from './sectorPerformanceSeries';

export type FolioOrderMarkerSide = 'buy' | 'sell' | 'sync';

export interface FolioOrderChartMarker {
  id: string;
  date: string;
  market: MarketCode;
  side: FolioOrderMarkerSide;
  ticker: string;
  name: string;
  nameZh?: string;
  nameEn?: string;
  qty: number;
  price: number;
  fillPrice?: number | null;
  fillTime?: string | null;
  orderTime?: string | null;
  x: number;
  y: number;
}

export function resolveFolioOrderDate(order: FolioOrder): string | null {
  const raw = order.fillTime ?? order.orderTime ?? order.createdAt;
  if (!raw) return null;
  return raw.slice(0, 10);
}

export interface FolioSyncOrderView {
  id: string;
  ticker: string;
  name: string;
  nameZh?: string;
  nameEn?: string;
  market: MarketCode;
  date: string;
  qty: number;
  price: number;
  syncNote?: string;
}

export interface FolioOrderEventView extends FolioSyncOrderView {
  side: FolioOrderMarkerSide;
  eventInstant: string;
}

export function resolveFolioOrderEventInstant(order: FolioOrder): string {
  return order.fillTime ?? order.orderTime ?? order.createdAt ?? '';
}

export function formatFolioOrderEventMinute(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const match = raw.match(/(?:T|\s)(\d{2}):(\d{2})/);
  if (!match) return null;
  return `${match[1]}:${match[2]}`;
}

export function isFolioSyncOrder(order: FolioOrder): boolean {
  return order.orderKind === 'sync' || order.orderSide === 'set';
}

function toOrderEventView(order: FolioOrder, side: FolioOrderMarkerSide, date: string): FolioOrderEventView {
  return {
    id: order.id,
    side,
    ticker: order.ticker,
    name: order.name,
    nameZh: order.nameZh,
    nameEn: order.nameEn,
    market: order.market,
    date,
    qty: order.qty,
    price: order.fillPrice ?? order.price,
    syncNote: order.syncNote,
    eventInstant: resolveFolioOrderEventInstant(order),
  };
}

export function collectFolioOrderEvents(
  orders: FolioOrder[],
  date: string,
  side: FolioOrderMarkerSide,
): FolioOrderEventView[] {
  const views: FolioOrderEventView[] = [];
  for (const order of orders) {
    if (order.orderStatus !== 'filled') continue;
    const orderSide = resolveMarkerSide(order);
    if (orderSide !== side) continue;
    const orderDate = resolveFolioOrderDate(order);
    if (orderDate !== date) continue;
    if (side === 'sync' && order.qty <= 0) {
      views.push(toOrderEventView(order, side, date));
      continue;
    }
    if (side !== 'sync' && order.qty <= 0) continue;
    views.push(toOrderEventView(order, side, date));
  }
  return views.sort((left, right) => {
    const byInstant = left.eventInstant.localeCompare(right.eventInstant);
    if (byInstant !== 0) return byInstant;
    return left.ticker.localeCompare(right.ticker) || left.id.localeCompare(right.id);
  });
}

export function collectFolioSyncOrders(orders: FolioOrder[]): FolioSyncOrderView[] {
  const views: FolioSyncOrderView[] = [];
  for (const order of orders) {
    if (order.orderStatus !== 'filled' || !isFolioSyncOrder(order)) continue;
    const date = resolveFolioOrderDate(order);
    if (!date) continue;
    views.push({
      id: order.id,
      ticker: order.ticker,
      name: order.name,
      nameZh: order.nameZh,
      nameEn: order.nameEn,
      market: order.market,
      date,
      qty: order.qty,
      price: order.fillPrice ?? order.price,
      syncNote: order.syncNote,
    });
  }
  return views.sort(
    (left, right) =>
      right.date.localeCompare(left.date) ||
      left.ticker.localeCompare(right.ticker) ||
      left.id.localeCompare(right.id),
  );
}

function resolveMarkerSide(order: FolioOrder): FolioOrderMarkerSide {
  if (order.orderKind === 'sync' || order.orderSide === 'set') {
    return 'sync';
  }
  return order.orderSide === 'sell' ? 'sell' : 'buy';
}

function resolveNavValue(
  series: MarketSeriesPoint[] | undefined,
  date: string,
): number | null {
  if (!series?.length) return null;
  const exact = series.find((point) => point.date === date);
  if (exact) return exact.value;
  const index = findVisibleIndexForDate(series, date);
  if (index == null) return null;
  return series[index]?.value ?? null;
}

export function buildFolioOrderChartMarkers(
  orders: FolioOrder[],
  visibleSeries: MarketSeriesPoint[],
  rebasedByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>,
  chartWidth: number,
  chartHeight: number,
  padX: number,
  padY: number,
): FolioOrderChartMarker[] {
  if (!visibleSeries.length) return [];

  const markers: FolioOrderChartMarker[] = [];
  for (const order of orders) {
    if (order.orderStatus !== 'filled') continue;
    const side = resolveMarkerSide(order);
    if (side === 'sync' && order.qty <= 0) continue;
    const date = resolveFolioOrderDate(order);
    if (!date) continue;

    const localIndex = findVisibleIndexForDate(visibleSeries, date);
    if (localIndex == null) continue;

    const navValue = resolveNavValue(rebasedByMarket[order.market], date);
    if (navValue == null || !Number.isFinite(navValue)) continue;

    const plotTop = padY;
    const plotBottom = chartHeight - padY;
    const plotMid = (plotTop + plotBottom) / 2;
    const markerY =
      side === 'buy' ? plotBottom - 5 : side === 'sell' ? plotTop + 5 : plotMid;

    markers.push({
      id: order.id,
      date,
      market: order.market,
      side,
      ticker: order.ticker,
      name: order.name,
      nameZh: order.nameZh,
      nameEn: order.nameEn,
      qty: order.qty,
      price: order.price,
      fillPrice: order.fillPrice,
      fillTime: order.fillTime,
      orderTime: order.orderTime,
      x: indexToChartX(localIndex, visibleSeries.length, chartWidth, padX),
      y: markerY,
    });
  }

  return markers;
}

export type FolioOrderTooltipPlacement =
  | 'above'
  | 'below'
  | 'above-left'
  | 'above-right'
  | 'below-left'
  | 'below-right';

export function resolveFolioOrderTooltipPlacement(
  marker: Pick<FolioOrderChartMarker, 'side' | 'x'>,
  chartWidth: number,
): FolioOrderTooltipPlacement {
  const edgeThreshold = 0.14;
  const xRatio = marker.x / chartWidth;
  const nearLeft = xRatio < edgeThreshold;
  const nearRight = xRatio > 1 - edgeThreshold;

  if (marker.side === 'sell') {
    if (nearRight) return 'below-left';
    if (nearLeft) return 'below-right';
    return 'below';
  }

  if (nearRight) return 'above-left';
  if (nearLeft) return 'above-right';
  return 'above';
}
