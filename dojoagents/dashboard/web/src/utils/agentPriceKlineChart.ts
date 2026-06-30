import { candleSlot, chartY, niceMinMax } from './entityCharts';

export interface AgentKlineBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface AgentPriceKlineLayout {
  width: number;
  priceHeight: number;
  volumeHeight: number;
  padX: number;
  padY: number;
  plotX0: number;
  plotW: number;
  priceMin: number;
  priceMax: number;
  maxVolume: number;
}

export function normalizeAgentKlineBar(
  raw: {
    datetime?: string | null;
    date?: string | null;
    open?: number | null;
    high?: number | null;
    low?: number | null;
    close?: number | null;
    volume?: number | null;
  },
): AgentKlineBar | null {
  const date = String(raw.date ?? raw.datetime ?? '').slice(0, 10);
  const open = Number(raw.open);
  const high = Number(raw.high);
  const low = Number(raw.low);
  const close = Number(raw.close);
  if (!date || ![open, high, low, close].every((v) => Number.isFinite(v))) {
    return null;
  }
  const volume = Number(raw.volume);
  return {
    date,
    open,
    high,
    low,
    close,
    volume: Number.isFinite(volume) ? volume : 0,
  };
}

export function buildAgentPriceKlineLayout(
  bars: AgentKlineBar[],
  width = 320,
  priceHeight = 96,
  volumeHeight = 28,
): AgentPriceKlineLayout | null {
  if (bars.length < 2) return null;
  const padX = 6;
  const padY = 6;
  const plotX0 = padX;
  const plotW = width - padX * 2;
  const priceBounds = niceMinMax(
    bars.flatMap((bar) => [bar.low, bar.high]),
    0.06,
  );
  const maxVolume = Math.max(...bars.map((bar) => bar.volume ?? 0), 1);
  return {
    width,
    priceHeight,
    volumeHeight,
    padX,
    padY,
    plotX0,
    plotW,
    priceMin: priceBounds.min,
    priceMax: priceBounds.max,
    maxVolume,
  };
}

export function barDirection(bar: AgentKlineBar): 'up' | 'down' | 'flat' {
  if (bar.close > bar.open) return 'up';
  if (bar.close < bar.open) return 'down';
  return 'flat';
}

export function priceY(
  value: number,
  layout: AgentPriceKlineLayout,
): number {
  return chartY(value, layout.priceMin, layout.priceMax, layout.priceHeight, layout.padY);
}

export function candleGeometry(
  bar: AgentKlineBar,
  index: number,
  count: number,
  layout: AgentPriceKlineLayout,
) {
  const { cx, barW } = candleSlot(index, count, layout.plotW, layout.plotX0);
  const openY = priceY(bar.open, layout);
  const closeY = priceY(bar.close, layout);
  const highY = priceY(bar.high, layout);
  const lowY = priceY(bar.low, layout);
  const bodyTop = Math.min(openY, closeY);
  const bodyHeight = Math.max(Math.abs(closeY - openY), 1);
  const volumeRatio = (bar.volume ?? 0) / layout.maxVolume;
  const volumeHeight = Math.max(volumeRatio * (layout.volumeHeight - 4), bar.volume ? 1.5 : 0);
  const volumeY = layout.volumeHeight - volumeHeight;
  return { cx, barW, highY, lowY, bodyTop, bodyHeight, volumeY, volumeHeight };
}
