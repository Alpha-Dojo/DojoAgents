import { useLayoutEffect, type RefObject } from 'react';
import {
  CORE_CHART_STRIP_H,
  CORE_CHART_TIME_H,
  CORE_CHART_TOPBAR_H,
  CORE_CHART_MIN_PLOT_H,
} from '../utils/coreChartLayout';

const CHART_CARD_SELECTOR = '.core-card--kline, .core-card--pe-band';
const BODY_SELECTOR = '.core-card__body';

/**
 * Measure the chart row and write one shared main-plot height to --core-synced-main-plot-h.
 * K-line candles and PE curve both use this row; date axis + bottom strip use fixed CSS heights.
 */
export function useSyncedChartSurfaceHeight(rowRef: RefObject<HTMLElement | null>): void {
  useLayoutEffect(() => {
    const row = rowRef.current;
    if (!row) return;

    const measure = () => {
      const cards = row.querySelectorAll<HTMLElement>(CHART_CARD_SELECTOR);
      if (cards.length < 2) return;

      let cardHeight = Infinity;
      cards.forEach((card) => {
        const h = card.getBoundingClientRect().height;
        if (h > 0) cardHeight = Math.min(cardHeight, h);
      });
      if (!Number.isFinite(cardHeight) || cardHeight <= 0) return;

      const body = cards[0].querySelector<HTMLElement>(BODY_SELECTOR);
      if (!body) return;

      const bodyStyle = getComputedStyle(body);
      const bodyPadY =
        parseFloat(bodyStyle.paddingTop) + parseFloat(bodyStyle.paddingBottom);
      const available = cardHeight - bodyPadY - CORE_CHART_TOPBAR_H;
      const mainPlotH = Math.max(
        CORE_CHART_MIN_PLOT_H,
        Math.floor(available - CORE_CHART_TIME_H - CORE_CHART_STRIP_H),
      );
      if (mainPlotH <= 0) return;

      row.style.setProperty('--core-synced-main-plot-h', `${mainPlotH}px`);
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(row);
    cardsInRow(row).forEach((el) => observer.observe(el));
    window.addEventListener('resize', measure);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [rowRef]);
}

function cardsInRow(row: HTMLElement): HTMLElement[] {
  return Array.from(row.querySelectorAll<HTMLElement>(CHART_CARD_SELECTOR));
}
