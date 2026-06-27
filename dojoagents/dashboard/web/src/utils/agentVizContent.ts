import type { AgentActivityStep } from '../types/agent';
import type { AgentVizBlock } from '../types/agentViz';

const MAX_PROMOTED_VIZ_BLOCKS = 4;
const CHART_BLOCK_KINDS = new Set([
  'sparkline',
  'line',
  'price_kline',
  'bar',
  'hbar_rank',
  'donut',
  'timeline',
]);

function stableSignature(value: unknown): string {
  if (value == null) return 'null';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.slice(0, 12).map((item) => stableSignature(item)).join(',')}]`;
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .slice(0, 20);
    return `{${entries.map(([key, entry]) => `${key}:${stableSignature(entry)}`).join(',')}}`;
  }
  return String(value);
}

function blockIdentity(block: AgentVizBlock): string {
  return [
    block.kind,
    block.source_tool ?? '',
    stableSignature(block.payload),
  ].join(':');
}

function normalizeMarket(value: unknown): string | null {
  const raw = String(value ?? '').trim().toLowerCase();
  if (raw === 'sh' || raw === 'sz') return 'cn';
  if (raw === 'us' || raw === 'cn' || raw === 'hk') return raw;
  return null;
}

function marketLabel(market: string): string {
  if (market === 'us') return 'US';
  if (market === 'cn') return 'CN';
  if (market === 'hk') return 'HK';
  return market.toUpperCase();
}

function synthesizeMarketOverviewBar(steps: AgentActivityStep[]): AgentVizBlock | null {
  const weightedPeByMarket = new Map<string, number>();
  for (const step of steps) {
    if (step.kind !== 'tool' || step.item.tool !== 'get_market_overview' || step.item.status !== 'done') {
      continue;
    }
    const markets = step.item.data?.markets;
    if (!markets || typeof markets !== 'object') continue;
    for (const [rawMarket, stats] of Object.entries(markets)) {
      if (!stats || typeof stats !== 'object') continue;
      const market = normalizeMarket(rawMarket);
      const weightedPe = Number((stats as Record<string, unknown>).weighted_pe);
      if (!market || !Number.isFinite(weightedPe)) continue;
      weightedPeByMarket.set(market, weightedPe);
    }
  }

  const orderedMarkets = ['us', 'cn', 'hk'].filter((market) => weightedPeByMarket.has(market));
  if (orderedMarkets.length < 2) return null;

  return {
    id: 'synth-market-overview-bar',
    kind: 'bar',
    title: 'Valuation comparison',
    subtitle: 'Weighted PE',
    source_tool: 'get_market_overview',
    payload: {
      categories: orderedMarkets.map((market) => marketLabel(market)),
      series: [
        {
          label: 'Weighted PE',
          values: orderedMarkets.map((market) => weightedPeByMarket.get(market) ?? null),
        },
      ],
    },
  };
}

export function attachDerivedVizBlocks(
  steps: AgentActivityStep[],
): AgentActivityStep[] {
  const hasMarketOverviewBar = steps.some(
    (step) =>
      step.kind === 'tool' &&
      step.item.tool === 'get_market_overview' &&
      (step.item.vizBlocks ?? []).some((block) => block.kind === 'bar'),
  );
  if (hasMarketOverviewBar) {
    return steps;
  }

  const synthesized = synthesizeMarketOverviewBar(steps);
  if (!synthesized) {
    return steps;
  }

  let targetIndex = -1;
  for (let index = steps.length - 1; index >= 0; index -= 1) {
    const step = steps[index];
    if (
      step.kind === 'tool' &&
      step.item.tool === 'get_market_overview' &&
      step.item.status === 'done'
    ) {
      targetIndex = index;
      break;
    }
  }

  if (targetIndex < 0) {
    return steps;
  }

  return steps.map((step, index) => {
    if (index !== targetIndex || step.kind !== 'tool') {
      return step;
    }
    const existingBlocks = step.item.vizBlocks ?? [];
    const identity = blockIdentity(synthesized);
    const alreadyPresent = existingBlocks.some(
      (block) => blockIdentity(block) === identity,
    );
    if (alreadyPresent) {
      return step;
    }
    return {
      ...step,
      item: {
        ...step.item,
        vizBlocks: [...existingBlocks, synthesized],
      },
    };
  });
}

export function collectVizBlocksFromSteps(steps: AgentActivityStep[]): AgentVizBlock[] {
  const seen = new Set<string>();
  const blocks: AgentVizBlock[] = [];
  for (const step of steps) {
    if (step.kind !== 'tool') continue;
    for (const block of step.item.vizBlocks ?? []) {
      const identity = blockIdentity(block);
      if (seen.has(identity)) continue;
      seen.add(identity);
      blocks.push(block);
      if (blocks.length >= MAX_PROMOTED_VIZ_BLOCKS) {
        return blocks;
      }
    }
  }
  const hasMarketOverviewBar = blocks.some(
    (block) => block.kind === 'bar' && block.source_tool === 'get_market_overview',
  );
  if (!hasMarketOverviewBar) {
    const synthesized = synthesizeMarketOverviewBar(steps);
    if (synthesized) {
      const identity = blockIdentity(synthesized);
      if (!seen.has(identity)) {
        blocks.push(synthesized);
      }
    }
  }
  return blocks;
}

export function hasRenderedChartBlocks(blocks: AgentVizBlock[]): boolean {
  return blocks.some((block) => CHART_BLOCK_KINDS.has(block.kind));
}

function shouldStripFence(info: string, body: string): boolean {
  const tag = info.trim().toUpperCase();
  if (tag === 'DOJO_CHART') return true;

  const normalized = body.trim();
  if (!normalized) return false;

  const looksLikeChartPayload =
    normalized.includes('chart.setOption(') &&
    normalized.includes('"script"') &&
    normalized.includes('"data"');
  if (!looksLikeChartPayload) return false;

  return tag === '' || tag === 'JSON' || tag === 'JS' || tag === 'JAVASCRIPT';
}

export function stripRenderedChartBlocks(content: string, enabled: boolean): string {
  if (!enabled || !content.trim()) return content;

  const next = content.replace(/```([^\n]*)\n([\s\S]*?)\n```/g, (full, info, body) =>
    shouldStripFence(String(info), String(body)) ? '' : full,
  );

  return next.replace(/\n{3,}/g, '\n\n').trim();
}
