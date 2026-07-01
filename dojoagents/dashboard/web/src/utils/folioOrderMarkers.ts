import type { FolioOrder } from '../types/folio';
import type { MarketCode } from '../types/market';
import { findVisibleIndexForDate, indexToChartX } from './sectorPerformanceSeries';
import type { MarketSeriesPoint } from './sectorPerformanceSeries';

export interface FolioOrderChartMarker {
  id: string;
  date: string;
  market: MarketCode;
  side: 'buy' | 'sell';
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

function resolveOrderDate(order: FolioOrder): string | null {
  const raw = order.fillTime ?? order.orderTime ?? order.createdAt;
  if (!raw) return null;
  return raw.slice(0, 10);
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
    const date = resolveOrderDate(order);
    if (!date) continue;

    const localIndex = findVisibleIndexForDate(visibleSeries, date);
    if (localIndex == null) continue;

    const navValue = resolveNavValue(rebasedByMarket[order.market], date);
    if (navValue == null || !Number.isFinite(navValue)) continue;

    const plotTop = padY;
    const plotBottom = chartHeight - padY;
    const markerY = order.orderSide === 'buy' ? plotBottom - 5 : plotTop + 5;

    markers.push({
      id: order.id,
      date,
      market: order.market,
      side: order.orderSide,
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
