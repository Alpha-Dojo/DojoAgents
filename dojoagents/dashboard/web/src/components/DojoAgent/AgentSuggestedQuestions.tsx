import { useEffect, useMemo, useState } from 'react';
import {
  resolveSuggestedQuestionContext,
  suggestedQuestionsForTab,
} from '../../agent/agentSuggestedQuestions';
import { useSectorTaxonomy } from '../../hooks/useSectorTaxonomy';
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
  const { taxonomy } = useSectorTaxonomy();
  const [contextTick, setContextTick] = useState(0);

  useEffect(() => {
    const bump = () => setContextTick((tick) => tick + 1);
    window.addEventListener('alphadojo-core-ticker', bump);
    window.addEventListener('alphadojo-sphere-selection', bump);
    return () => {
      window.removeEventListener('alphadojo-core-ticker', bump);
      window.removeEventListener('alphadojo-sphere-selection', bump);
    };
  }, []);

  const context = useMemo(
    () => resolveSuggestedQuestionContext(locale, taxonomy),
    [locale, taxonomy, contextTick],
  );
  const questions = suggestedQuestionsForTab(sourceTab, locale, context);

  return (
    <div className="dojo-agent-panel__suggested" aria-label={t('agent.suggestedTitle')}>
      <p className="dojo-agent-panel__suggested-hint">{t(TAB_HINT_KEYS[sourceTab])}</p>
      <ul className="dojo-agent-panel__suggested-list">
        {questions.map((question) => (
          <li key={question}>
            <button
              type="button"
              className="dojo-agent-panel__suggested-item base-card"
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
