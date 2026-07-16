import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type {
  MarketDynamicsEvent,
  MarketDynamicsSectorImpact,
} from '../../types/marketDynamics';
import type { MarketCode } from '../../types/market';
import { useTranslation } from '../../hooks/useTranslation';
import type { AppLocale } from '../../i18n/locale';
import { DEFAULT_MARKET_ORDER } from '../../navigation/marketColumnOrder';
import {
  buildImpactDetailLinks,
  categoryColor,
  categoryLabelKey,
  eventCalendarDate,
  formatEventTime,
  surpriseClass,
  surpriseLabelKey,
} from '../../utils/marketDynamicsFormat';
import { MarketEventDetailPanel } from './MarketEventDetailPanel';
import { MarketEventImpactConnector } from './MarketEventImpactConnector';
import { LoadingIndicator } from '../ui/LoadingIndicator';
import './MarketEventTimeline.css';

/** Trigger prefetch when remaining scroll distance is within this many card widths. */
const EDGE_CARD_THRESHOLD = 2.5;

interface MarketEventTimelineProps {
  events: MarketDynamicsEvent[];
  /** Left-to-right market column order on the Market page (US/CN/HK). */
  marketOrder?: MarketCode[];
  /** Clears selection when this identity changes (date / category / etc.). */
  selectionResetKey?: string;
  focusDate?: string | null;
  loading?: boolean;
  loadingMore?: boolean;
  error?: string | null;
  hasMoreBefore?: boolean;
  hasMoreAfter?: boolean;
  onNearStart?: () => void;
  onNearEnd?: () => void;
  onRetry?: () => void;
  onSectorJump?: (impact: MarketDynamicsSectorImpact) => void;
}

interface TimelineCardView {
  id: string;
  event: MarketDynamicsEvent;
  eventDate: string | null;
  showDateMarker: boolean;
  markerLabel: string;
  timeLabel: string;
  headline: string;
  category: string;
  surprise: string;
}

function scrollToEnd(el: HTMLElement | null) {
  if (!el) return;
  el.scrollLeft = Math.max(el.scrollWidth - el.clientWidth, 0);
}

function buildCardViews(
  events: MarketDynamicsEvent[],
  locale: AppLocale,
  resolveHeadline: (event: MarketDynamicsEvent) => string,
): TimelineCardView[] {
  let prevDate: string | null = null;
  return events.map((event) => {
    const eventDate = eventCalendarDate(event.event_time, locale);
    const showDateMarker = Boolean(eventDate && eventDate !== prevDate);
    prevDate = eventDate;
    const category = event.event_summary?.category ?? 'market_structure';
    return {
      id: event.id,
      event,
      eventDate,
      showDateMarker,
      markerLabel: eventDate ? eventDate.slice(5) : '',
      timeLabel: event.event_time ? formatEventTime(event.event_time, locale) : '—',
      headline: resolveHeadline(event),
      category,
      surprise: event.event_summary?.surprise ?? 'expected',
    };
  });
}

interface EventCardProps {
  card: TimelineCardView;
  active: boolean;
  linked: boolean;
  categoryLabel: string;
  surpriseLabel: string;
  onSelect: (eventId: string, isActive: boolean) => void;
}

const EventCard = memo(function EventCard({
  card,
  active,
  linked,
  categoryLabel,
  surpriseLabel,
  onSelect,
}: EventCardProps) {
  return (
    <div className="event-timeline__item">
      {card.showDateMarker && card.eventDate ? (
        <div className="event-timeline__marker" data-event-date={card.eventDate}>
          <span className="event-timeline__marker-line" />
          <span className="event-timeline__marker-label">{card.markerLabel}</span>
        </div>
      ) : null}
      <button
        type="button"
        data-event-id={card.id}
        data-event-date={card.eventDate ?? undefined}
        data-connector-card={active ? card.id : undefined}
        className={`event-timeline__card${active ? ' event-timeline__card--active' : ''}${
          linked ? ' event-timeline__card--linked' : ''
        }`}
        onClick={() => onSelect(card.id, active)}
        aria-expanded={active}
      >
        <span className="event-timeline__card-time">{card.timeLabel}</span>
        <h4 className="event-timeline__card-title">{card.headline || '—'}</h4>
        <div className="event-timeline__card-tags">
          <span className="badge badge--category">
            <span className="chip__dot" style={{ background: categoryColor(card.category) }} />
            {categoryLabel}
          </span>
          <span className={`badge badge--surprise ${surpriseClass(card.surprise)}`}>
            {surpriseLabel}
          </span>
        </div>
      </button>
    </div>
  );
});

export const MarketEventTimeline = memo(function MarketEventTimeline({
  events,
  marketOrder = DEFAULT_MARKET_ORDER,
  selectionResetKey = '',
  focusDate = null,
  loading = false,
  loadingMore = false,
  error = null,
  hasMoreBefore = false,
  hasMoreAfter = false,
  onNearStart,
  onNearEnd,
  onRetry,
  onSectorJump,
}: MarketEventTimelineProps) {
  const { locale, t, text } = useTranslation();
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const connectorHostRef = useRef<HTMLElement>(null);
  const prevFocusDateRef = useRef<string | null>(null);
  const prevSelectedEventIdRef = useRef<string | null>(null);
  const prevFirstIdRef = useRef<string>('');
  const prevScrollWidthRef = useRef(0);
  const prevScrollLeftRef = useRef(0);
  const didInitialScrollRef = useRef(false);
  const nearStartArmed = useRef(true);
  const nearEndArmed = useRef(true);

  useEffect(() => {
    setSelectedEventId(null);
  }, [selectionResetKey, focusDate]);

  useEffect(() => {
    setSelectedEventId((prev) =>
      prev && events.some((event) => event.id === prev) ? prev : null,
    );
  }, [events]);

  const cards = useMemo(
    () =>
      buildCardViews(events, locale, (event) =>
        text(event.event_summary?.headline ?? { zh: '', en: '' }),
      ),
    [events, locale, text],
  );

  const eventsByDate = useMemo(() => {
    const map = new Map<string, MarketDynamicsEvent[]>();
    for (const card of cards) {
      if (!card.eventDate) continue;
      const bucket = map.get(card.eventDate);
      if (bucket) bucket.push(card.event);
      else map.set(card.eventDate, [card.event]);
    }
    return map;
  }, [cards]);

  const categoryLabels = useMemo(() => {
    const labels = new Map<string, string>();
    for (const card of cards) {
      if (!labels.has(card.category)) {
        labels.set(card.category, t(categoryLabelKey(card.category)));
      }
    }
    return labels;
  }, [cards, t]);

  const surpriseLabels = useMemo(() => {
    const labels = new Map<string, string>();
    for (const card of cards) {
      if (!labels.has(card.surprise)) {
        labels.set(card.surprise, t(surpriseLabelKey(card.surprise)));
      }
    }
    return labels;
  }, [cards, t]);

  const selectedEvent = useMemo(
    () => events.find((event) => event.id === selectedEventId) ?? null,
    [events, selectedEventId],
  );

  const detailImpacts = useMemo(
    () => selectedEvent?.sector_impacts ?? [],
    [selectedEvent],
  );

  const impactDetailLinks = useMemo(
    () => buildImpactDetailLinks(detailImpacts),
    [detailImpacts],
  );

  const showImpactConnector =
    selectedEventId !== null && selectedEvent !== null && impactDetailLinks.length > 0;

  const scrollTrackToDate = useCallback((date: string) => {
    trackRef.current
      ?.querySelector<HTMLElement>(`[data-event-date="${date}"]`)
      ?.scrollIntoView({ behavior: 'instant', inline: 'start', block: 'nearest' });
  }, []);

  const jumpToFocusOrEnd = useCallback(() => {
    if (cards.length === 0) return;
    const lastDate = cards[cards.length - 1]?.eventDate;
    const preferred =
      (focusDate && eventsByDate.has(focusDate) ? focusDate : null) ?? lastDate;
    if (preferred && eventsByDate.has(preferred)) {
      scrollTrackToDate(preferred);
      return;
    }
    scrollToEnd(trackRef.current);
  }, [cards, eventsByDate, focusDate, scrollTrackToDate]);

  useLayoutEffect(() => {
    const track = trackRef.current;
    const firstId = cards[0]?.id ?? '';

    if (!didInitialScrollRef.current && cards.length > 0) {
      didInitialScrollRef.current = true;
      jumpToFocusOrEnd();
    } else if (
      track &&
      firstId &&
      prevFirstIdRef.current &&
      firstId !== prevFirstIdRef.current
    ) {
      const delta = track.scrollWidth - prevScrollWidthRef.current;
      track.scrollLeft = prevScrollLeftRef.current + Math.max(delta, 0);
    }

    prevFirstIdRef.current = firstId;
    if (track) {
      prevScrollWidthRef.current = track.scrollWidth;
      prevScrollLeftRef.current = track.scrollLeft;
    }
  }, [cards, jumpToFocusOrEnd]);

  useLayoutEffect(() => {
    if (!focusDate || focusDate === prevFocusDateRef.current) return;
    prevFocusDateRef.current = focusDate;
    if (!eventsByDate.has(focusDate)) return;
    scrollTrackToDate(focusDate);
    nearStartArmed.current = true;
    nearEndArmed.current = true;
  }, [focusDate, eventsByDate, scrollTrackToDate]);

  useLayoutEffect(() => {
    if (cards.length === 0) {
      didInitialScrollRef.current = false;
      prevFirstIdRef.current = '';
    }
  }, [cards.length, focusDate]);

  useLayoutEffect(() => {
    if (!selectedEventId) {
      prevSelectedEventIdRef.current = null;
      return;
    }
    const selectionChanged = prevSelectedEventIdRef.current !== selectedEventId;
    prevSelectedEventIdRef.current = selectedEventId;
    if (!selectionChanged) return;

    trackRef.current
      ?.querySelector<HTMLElement>(`[data-event-id="${selectedEventId}"]`)
      ?.scrollIntoView({ behavior: 'instant', inline: 'nearest', block: 'nearest' });
  }, [selectedEventId]);

  const handleScroll = useCallback(() => {
    const el = trackRef.current;
    if (!el) return;
    prevScrollLeftRef.current = el.scrollLeft;
    prevScrollWidthRef.current = el.scrollWidth;

    const cardWidth = el.querySelector<HTMLElement>('.event-timeline__item')?.offsetWidth ?? 160;
    const threshold = cardWidth * EDGE_CARD_THRESHOLD;
    const maxScroll = Math.max(el.scrollWidth - el.clientWidth, 0);

    if (el.scrollLeft <= threshold) {
      if (nearStartArmed.current && hasMoreBefore && onNearStart) {
        nearStartArmed.current = false;
        onNearStart();
      }
    } else {
      nearStartArmed.current = true;
    }

    if (maxScroll - el.scrollLeft <= threshold) {
      if (nearEndArmed.current && hasMoreAfter && onNearEnd) {
        nearEndArmed.current = false;
        onNearEnd();
      }
    } else {
      nearEndArmed.current = true;
    }
  }, [hasMoreBefore, hasMoreAfter, onNearStart, onNearEnd]);

  useLayoutEffect(() => {
    if (!loadingMore) {
      nearStartArmed.current = true;
      nearEndArmed.current = true;
      handleScroll();
    }
  }, [loadingMore, cards.length, handleScroll]);

  const handleCardClick = useCallback((eventId: string, isActive: boolean) => {
    setSelectedEventId(isActive ? null : eventId);
  }, []);

  if (loading && events.length === 0) {
    return (
      <section className="event-timeline event-timeline--status" aria-busy="true">
        <LoadingIndicator
          className="event-timeline__status"
          label={t('marketPage.eventTimelineLoading')}
          variant="inline"
        />
      </section>
    );
  }

  if (error && events.length === 0) {
    return (
      <section className="event-timeline event-timeline--status">
        <p className="event-timeline__empty">
          {t('marketPage.eventTimelineLoadFailed')}
          {error ? ` · ${error}` : ''}
        </p>
        {onRetry ? (
          <button type="button" className="event-timeline__retry" onClick={onRetry}>
            {t('marketPage.retry')}
          </button>
        ) : null}
      </section>
    );
  }

  if (events.length === 0) {
    return (
      <section className="event-timeline">
        <p className="event-timeline__empty">{t('marketPage.eventTimelineEmpty')}</p>
      </section>
    );
  }

  return (
    <section ref={connectorHostRef} className="event-timeline event-timeline--connector-host">
      <div className="event-timeline__track" ref={trackRef} onScroll={handleScroll}>
        {cards.map((card) => {
          const active = card.id === selectedEventId;
          return (
            <EventCard
              key={card.id}
              card={card}
              active={active}
              linked={active && showImpactConnector}
              categoryLabel={categoryLabels.get(card.category) ?? card.category}
              surpriseLabel={surpriseLabels.get(card.surprise) ?? card.surprise}
              onSelect={handleCardClick}
            />
          );
        })}
      </div>

      {selectedEvent ? (
        <MarketEventDetailPanel
          event={selectedEvent}
          impacts={detailImpacts}
          marketOrder={marketOrder}
          onSectorJump={onSectorJump}
        />
      ) : null}

      <MarketEventImpactConnector
        hostRef={connectorHostRef}
        eventId={selectedEventId}
        links={impactDetailLinks}
        active={showImpactConnector}
      />
    </section>
  );
});
