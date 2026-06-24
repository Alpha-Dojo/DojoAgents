export type AgentVizKind =
  | 'kpi_row'
  | 'sparkline'
  | 'line'
  | 'bar'
  | 'hbar_rank'
  | 'donut'
  | 'table'
  | 'timeline'
  | 'quote_card';

export interface AgentVizBlock {
  id: string;
  kind: AgentVizKind;
  title: string;
  subtitle?: string | null;
  source_tool?: string;
  truncated?: boolean;
  payload: Record<string, unknown>;
}

export interface AgentVizKpiItem {
  key?: string;
  label: string;
  value?: string | number | null;
  value_format?: string;
  meta?: string | null;
  delta?: string | null;
  tone?: 'positive' | 'negative' | 'neutral' | 'risk' | null;
}

export interface AgentVizMarketKpiGroup {
  market: string;
  items: AgentVizKpiItem[];
}

export interface AgentVizTableGroup {
  market: string;
  rows: Record<string, unknown>[];
}

export interface AgentVizTableColumn {
  key: string;
  label: string;
  format?: string;
}

export interface AgentVizSeriesPoint {
  date?: string | null;
  value?: number | null;
}

export interface AgentVizLineSeries {
  id: string;
  label: string;
  market?: string;
  points: AgentVizSeriesPoint[];
  dashed?: boolean;
}

export interface AgentVizDonutSlice {
  key: string;
  label: string;
  value: number;
  market?: string;
}

export interface AgentVizRankItem {
  label: string;
  value: number;
}

export interface AgentVizTimelineItem {
  kind?: string;
  date?: string | null;
  title?: string;
  summary?: string;
  source?: string | null;
}
