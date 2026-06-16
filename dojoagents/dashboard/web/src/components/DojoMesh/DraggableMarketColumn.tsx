import type { DragEvent, HTMLAttributes, ReactNode } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/dojoMesh';

export type MarketBrandDragProps = HTMLAttributes<HTMLDivElement> & {
  draggable: true;
};

interface DraggableMarketColumnProps {
  market: MarketCode;
  isDragging: boolean;
  isDropTarget: boolean;
  onDragStart: (market: MarketCode) => void;
  onDragEnd: () => void;
  onDragOver: (market: MarketCode) => void;
  onDrop: (market: MarketCode) => void;
  children: (brandDrag: MarketBrandDragProps) => ReactNode;
}

export function DraggableMarketColumn({
  market,
  isDragging,
  isDropTarget,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDrop,
  children,
}: DraggableMarketColumnProps) {
  const { t } = useTranslation();

  const brandDrag: MarketBrandDragProps = {
    draggable: true,
    'aria-label': t('mesh.dragColumn'),
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
        isDropTarget ? ' mesh-market-column-wrap--drop-target' : ''
      }`}
      onDragOver={(event) => {
        event.preventDefault();
        onDragOver(market);
      }}
      onDrop={(event) => {
        event.preventDefault();
        onDrop(market);
      }}
    >
      {children(brandDrag)}
    </div>
  );
}
