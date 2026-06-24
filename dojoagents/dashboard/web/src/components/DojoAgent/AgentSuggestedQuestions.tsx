import { suggestedQuestionsForTab } from '../../agent/agentSuggestedQuestions';
import { useTranslation } from '../../hooks/useTranslation';
import type { AppTab } from '../../navigation/appTab';

interface AgentSuggestedQuestionsProps {
  sourceTab: AppTab;
  onSelect: (question: string) => void;
}

const TAB_HINT_KEYS: Record<AppTab, string> = {
  mesh: 'agent.suggestedHintMesh',
  sphere: 'agent.suggestedHintSphere',
  core: 'agent.suggestedHintCore',
  folio: 'agent.suggestedHintFolio',
};

export function AgentSuggestedQuestions({ sourceTab, onSelect }: AgentSuggestedQuestionsProps) {
  const { t, locale } = useTranslation();
  const questions = suggestedQuestionsForTab(sourceTab, locale);

  return (
    <div className="dojo-agent-panel__suggested" aria-label={t('agent.suggestedTitle')}>
      <p className="dojo-agent-panel__suggested-hint">{t(TAB_HINT_KEYS[sourceTab])}</p>
      <ul className="dojo-agent-panel__suggested-list">
        {questions.map((question) => (
          <li key={question}>
            <button
              type="button"
              className="dojo-agent-panel__suggested-item"
              onClick={() => onSelect(question)}
            >
              {question}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
