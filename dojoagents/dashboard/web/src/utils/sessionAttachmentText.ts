import type { AgentSessionInputFile } from '../types/agent';

export function formatSessionAttachmentsForPrompt(
  attachments: AgentSessionInputFile[],
  locale: 'zh' | 'en',
): string {
  if (attachments.length === 0) return '';
  const header = locale === 'zh' ? '## 用户上传文件' : '## Attached Files';
  const lines = [header];
  for (const file of attachments) {
    lines.push(`- \`${file.filename}\` (${file.kind}) → \`${file.path}\``);
    if (file.summary) {
      lines.push(`  - ${file.summary}`);
    }
    if (file.preview_text) {
      lines.push('  ```');
      lines.push(file.preview_text);
      lines.push('  ```');
    }
  }
  return lines.join('\n');
}
