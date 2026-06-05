// DOJO_CHART block extraction utility
// Parses chart rendering payloads embedded in Agent text responses.
//
// Protocol: Agent outputs a fenced code block tagged DOJO_CHART containing
// a JSON object with { data, script } fields. The frontend extracts this
// block and sends it to the Canvas iframe for ECharts rendering.

export interface DojoChartPayload {
  data: unknown
  script: string
}

/** Regex matching a ```DOJO_CHART fenced code block (non-greedy). */
export const CHART_RE = /```DOJO_CHART\n([\s\S]*?)\n```/

/**
 * Extract and parse the first DOJO_CHART block from `text`.
 *
 * Returns the parsed `{ data, script }` payload on success, or `null` if:
 * - No DOJO_CHART block is found (e.g. during streaming, block not yet complete)
 * - The JSON inside the block is malformed
 * - The parsed value is not an object with the expected shape
 */
export function extractDojoChart(text: string): DojoChartPayload | null {
  const match = text.match(CHART_RE)
  if (!match) return null

  try {
    const parsed = JSON.parse(match[1])
    if (parsed && typeof parsed === 'object' && typeof parsed.script === 'string') {
      return parsed as DojoChartPayload
    }
  } catch {
    // Malformed JSON — may still be streaming, return null
  }
  return null
}
