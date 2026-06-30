import type { DragEvent, HTMLAttributes, ReactNode } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketDropSide } from '../../navigation/marketColumnOrder';
import type { MarketCode } from '../../types/market';

export type MarketBrandDragProps = HTMLAttributes<HTMLDivElement> & {
  draggable: true;
};

interface DraggableMarketColumnProps {
  market: MarketCode;
  isDragging: boolean;
  dropSide: MarketDropSide | null;
  onDragStart: (market: MarketCode) => void;
  onDragEnd: () => void;
  onDragOver: (market: MarketCode, side: MarketDropSide) => void;
  onDrop: (market: MarketCode, side: MarketDropSide) => void;
  children: (brandDrag: MarketBrandDragProps) => ReactNode;
}

function getDropSide(event: DragEvent<HTMLDivElement>): MarketDropSide {
  const rect = event.currentTarget.getBoundingClientRect();
  const offset = event.clientX - rect.left;
  const ratio = rect.width > 0 ? offset / rect.width : 0;
  return ratio > 0.5 ? 'right' : 'left';
}

export function DraggableMarketColumn({
  market,
  isDragging,
  dropSide,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDrop,
  children,
}: DraggableMarketColumnProps) {
  const { t } = useTranslation();

  const brandDrag: MarketBrandDragProps = {
    draggable: true,
    'aria-label': t('marketPage.dragColumn'),
    title: t('marketPage.dragColumn'),
    onDragStart: (event: DragEvent<HTMLDivElement>) => {
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', market);
      onDragStart(market);
    },
    onDragEnd,
  };

  return (
    <div
      className={`mesh-market-column-wrap${isDragging ? ' mesh-market-column-wrap--dragging' : ''}${
        dropSide ? ` mesh-market-column-wrap--drop-target mesh-market-column-wrap--drop-${dropSide}` : ''
      }`}
      onDragEnter={(event) => {
        event.preventDefault();
        onDragOver(market, getDropSide(event));
      }}
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        onDragOver(market, getDropSide(event));
      }}
      onDrop={(event) => {
        event.preventDefault();
        onDrop(market, getDropSide(event));
      }}
    >
      {children(brandDrag)}
    </div>
  );
}
