import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface AgentMarkdownProps {
  content: string;
  streaming?: boolean;
}

export function AgentMarkdown({ content, streaming = false }: AgentMarkdownProps) {
  if (!content.trim()) return null;

  return (
    <div
      className={`dojo-agent-md ${streaming ? 'dojo-agent-md--streaming' : ''}`}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
