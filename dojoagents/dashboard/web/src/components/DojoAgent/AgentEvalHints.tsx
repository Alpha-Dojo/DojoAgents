import { useTranslation } from '../../hooks/useTranslation';

interface AgentEvalHintsProps {
  issues: string[];
}

export function AgentEvalHints({ issues }: AgentEvalHintsProps) {
  const { t } = useTranslation();
  if (issues.length === 0) return null;

  return (
    <div className="dojo-agent-eval" role="status" aria-live="polite">
      <p className="dojo-agent-eval__title">{t('agent.evalTitle')}</p>
      <ul className="dojo-agent-eval__list">
        {issues.map((issue) => (
          <li key={issue}>{issue}</li>
        ))}
      </ul>
    </div>
  );
}
