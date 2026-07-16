import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { buildImpactDetailLinks, directionColor } from '../../utils/marketDynamicsFormat';
import './MarketEventTimeline.css';

interface Point {
  x: number;
  y: number;
}

interface BusDrop {
  id: string;
  color: string;
  x: number;
  y1: number;
  y2: number;
}

interface BusGeometry {
  trunk: { x: number; y1: number; y2: number } | null;
  bus: { x1: number; x2: number; y: number } | null;
  drops: BusDrop[];
}

interface MarketEventImpactConnectorProps {
  hostRef: RefObject<HTMLElement | null>;
  eventId: string | null;
  links: ReturnType<typeof buildImpactDetailLinks>;
  active: boolean;
}

const BUS_GAP = 10;
const MIN_TRUNK = 14;

function anchorPoint(el: Element, hostRect: DOMRect, edge: 'top' | 'bottom'): Point {
  const rect = el.getBoundingClientRect();
  return {
    x: rect.left + rect.width / 2 - hostRect.left,
    y: (edge === 'top' ? rect.top : rect.bottom) - hostRect.top,
  };
}

function resolveBusGeometry(
  host: HTMLElement,
  eventId: string,
  links: ReturnType<typeof buildImpactDetailLinks>,
): BusGeometry | null {
  const hostRect = host.getBoundingClientRect();
  const card = host.querySelector(`[data-connector-card="${CSS.escape(eventId)}"]`);
  if (!card) return null;

  const cardRect = card.getBoundingClientRect();
  const cardBottom = cardRect.bottom - hostRect.top;
  const cardCenterX = cardRect.left + cardRect.width / 2 - hostRect.left;

  const drops: BusDrop[] = [];
  const targetXs: number[] = [];

  links.forEach((link) => {
    const target = host.querySelector(`[data-connector-pill="${CSS.escape(link.impactSectorId)}"]`);
    if (!target) return;

    const to = anchorPoint(target, hostRect, 'top');
    if (to.y <= cardBottom + 4) return;

    targetXs.push(to.x);
    drops.push({
      id: link.impactSectorId,
      color: directionColor(link.direction),
      x: to.x,
      y1: 0,
      y2: to.y,
    });
  });

  if (drops.length === 0) return null;

  const minTargetY = Math.min(...drops.map((drop) => drop.y2));
  const busY = Math.max(cardBottom + MIN_TRUNK, minTargetY - BUS_GAP);
  const busX1 = Math.min(cardCenterX, ...targetXs);
  const busX2 = Math.max(cardCenterX, ...targetXs);

  for (const drop of drops) {
    drop.y1 = busY;
  }

  return {
    trunk: { x: cardCenterX, y1: cardBottom, y2: busY },
    bus: { x1: busX1, x2: busX2, y: busY },
    drops,
  };
}

function syncLinkedTargets(
  host: HTMLElement | null,
  links: ReturnType<typeof buildImpactDetailLinks>,
  active: boolean,
) {
  if (!host) return;
  host.querySelectorAll<HTMLElement>('[data-connector-pill]').forEach((el) => {
    el.classList.remove('ed-connector-target--linked');
  });
  if (!active) return;

  for (const link of links) {
    host
      .querySelector<HTMLElement>(`[data-connector-pill="${CSS.escape(link.impactSectorId)}"]`)
      ?.classList.add('ed-connector-target--linked');
  }
}

/**
 * Draws connector lines after the detail panel has painted (deferred),
 * and only remeasures on host resize / local scroll — not global scroll.
 */
export function MarketEventImpactConnector({
  hostRef,
  eventId,
  links,
  active,
}: MarketEventImpactConnectorProps) {
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [geometry, setGeometry] = useState<BusGeometry | null>(null);
  const frameRef = useRef<number | null>(null);
  const readyFrameRef = useRef<number | null>(null);

  const linkSignature = useMemo(
    () => `${eventId ?? ''}|${links.map((link) => link.impactSectorId).join('|')}`,
    [eventId, links],
  );

  const measure = useCallback(() => {
    const host = hostRef.current;
    if (!host || !active || !eventId || links.length === 0) {
      setGeometry(null);
      syncLinkedTargets(host, links, false);
      return;
    }

    const rect = host.getBoundingClientRect();
    setSize({ width: Math.max(rect.width, 1), height: Math.max(rect.height, 1) });
    setGeometry(resolveBusGeometry(host, eventId, links));
    syncLinkedTargets(host, links, true);
  }, [active, eventId, hostRef, links]);

  useEffect(() => {
    const host = hostRef.current;
    if (!active || !eventId || links.length === 0) {
      setGeometry(null);
      syncLinkedTargets(host, links, false);
      return;
    }

    let cancelled = false;

    const schedule = () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      frameRef.current = requestAnimationFrame(() => {
        frameRef.current = null;
        if (!cancelled) measure();
      });
    };

    // Let the detail panel commit/paint first, then measure (avoids blocking click).
    readyFrameRef.current = requestAnimationFrame(() => {
      readyFrameRef.current = requestAnimationFrame(() => {
        readyFrameRef.current = null;
        if (!cancelled) measure();
      });
    });

    if (!host) {
      return () => {
        cancelled = true;
      };
    }

    const observer = new ResizeObserver(schedule);
    observer.observe(host);
    host.addEventListener('scroll', schedule, true);
    window.addEventListener('resize', schedule);

    return () => {
      cancelled = true;
      observer.disconnect();
      host.removeEventListener('scroll', schedule, true);
      window.removeEventListener('resize', schedule);
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      if (readyFrameRef.current !== null) cancelAnimationFrame(readyFrameRef.current);
      syncLinkedTargets(host, links, false);
    };
  }, [hostRef, measure, linkSignature, active, eventId, links]);

  if (!active || !geometry || geometry.drops.length === 0 || size.width <= 0) return null;

  const { trunk, bus, drops } = geometry;

  return (
    <svg
      className="impact-connector"
      width={size.width}
      height={size.height}
      viewBox={`0 0 ${size.width} ${size.height}`}
      aria-hidden
    >
      {trunk ? (
        <line
          className="impact-connector__trunk"
          x1={trunk.x}
          y1={trunk.y1}
          x2={trunk.x}
          y2={trunk.y2}
        />
      ) : null}
      {bus ? (
        <line
          className="impact-connector__bus"
          x1={bus.x1}
          y1={bus.y}
          x2={bus.x2}
          y2={bus.y}
        />
      ) : null}
      {trunk && bus ? (
        <circle className="impact-connector__junction" cx={trunk.x} cy={bus.y} r={2.5} />
      ) : null}
      {drops.map((drop) => (
        <g key={drop.id}>
          <line
            className="impact-connector__drop"
            x1={drop.x}
            y1={drop.y1}
            x2={drop.x}
            y2={drop.y2}
            stroke={drop.color}
          />
          <circle className="impact-connector__tap" cx={drop.x} cy={drop.y1} r={2} fill={drop.color} />
        </g>
      ))}
    </svg>
  );
}
