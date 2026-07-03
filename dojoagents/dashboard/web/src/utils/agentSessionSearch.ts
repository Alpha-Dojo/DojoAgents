import type { AgentSession } from '../types/agent';

export function filterAgentSessionsByTitle(
  sessions: AgentSession[],
  query: string,
): AgentSession[] {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (!normalizedQuery) return sessions;
  return sessions.filter((session) =>
    session.title.toLocaleLowerCase().includes(normalizedQuery),
  );
}
