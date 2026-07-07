import { ApiError } from '../api/http';

import type { AgentSessionInputFile } from '../types/agent';

const SESSION_API_PREFIX = '/api/v1/chat/sessions';

export const AGENT_MAX_FILE_ATTACHMENTS = 5;
export const AGENT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

export const AGENT_UPLOAD_ACCEPT = [
  '.txt',
  '.md',
  '.markdown',
  '.csv',
  '.tsv',
  '.json',
  '.jsonl',
  '.yaml',
  '.yml',
  '.toml',
  '.xml',
  '.html',
  '.htm',
  '.css',
  '.sql',
  '.py',
  '.ts',
  '.tsx',
  '.js',
  '.jsx',
  '.java',
  '.go',
  '.rs',
  '.rb',
  '.php',
  '.swift',
  '.kt',
  '.c',
  '.cpp',
  '.h',
  '.hpp',
  '.sh',
  '.xlsx',
  '.xls',
  '.pdf',
].join(',');

const SUPPORTED_SUFFIXES = new Set(
  AGENT_UPLOAD_ACCEPT.split(',').map((item) => item.trim().toLowerCase()).filter(Boolean),
);

function fileSuffix(name: string): string {
  const index = name.lastIndexOf('.');
  return index >= 0 ? name.slice(index).toLowerCase() : '';
}

export function isSupportedUploadFile(file: File): boolean {
  const suffix = fileSuffix(file.name);
  return SUPPORTED_SUFFIXES.has(suffix);
}

async function readErrorMessage(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { error?: string; detail?: string };
    if (typeof body.error === 'string') return body.error;
    if (typeof body.detail === 'string') return body.detail;
  } catch {
    // ignore
  }
  return `Request failed: ${res.status} ${res.statusText}`;
}

export async function uploadSessionInputFile(
  sessionId: string,
  file: File,
): Promise<AgentSessionInputFile> {
  if (!isSupportedUploadFile(file)) {
    throw new Error('unsupported file type');
  }
  if (file.size > AGENT_MAX_UPLOAD_BYTES) {
    throw new Error('file too large');
  }
  const form = new FormData();
  form.append('file', file, file.name);
  const res = await fetch(`${SESSION_API_PREFIX}/${encodeURIComponent(sessionId)}/inputs`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    throw new ApiError(await readErrorMessage(res), res.status);
  }
  const body = (await res.json()) as { file: AgentSessionInputFile };
  return body.file;
}
