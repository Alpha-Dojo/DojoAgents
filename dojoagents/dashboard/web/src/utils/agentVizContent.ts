import type { AgentActivityStep } from '../types/agent';
import type { AgentVizBlock } from '../types/agentViz';

function blockIdentity(block: AgentVizBlock): string {
  return block.id || `${block.kind}:${block.title}:${block.subtitle ?? ''}`;
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
    }
  }
  return blocks;
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
