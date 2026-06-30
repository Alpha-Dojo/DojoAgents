import type { AgentChatImageAttachment } from '../types/agent';

export const AGENT_MAX_IMAGE_ATTACHMENTS = 4;
export const AGENT_MAX_IMAGE_BYTES = 5 * 1024 * 1024;

const DATA_IMAGE_URL_RE = /^data:image\/[a-zA-Z0-9.+-]+;base64,/;

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        resolve(reader.result);
        return;
      }
      reject(new Error('invalid image data'));
    };
    reader.onerror = () => reject(reader.error ?? new Error('failed to read image'));
    reader.readAsDataURL(file);
  });
}

function estimateDataUrlBytes(dataUrl: string): number {
  const comma = dataUrl.indexOf(',');
  if (comma < 0) return dataUrl.length;
  const payload = dataUrl.slice(comma + 1);
  return Math.floor((payload.length * 3) / 4);
}

function attachmentFromDataUrl(dataUrl: string, name?: string): AgentChatImageAttachment {
  return { dataUrl, name };
}

export async function createImageAttachmentFromDataUrl(
  dataUrl: string,
  name?: string,
): Promise<AgentChatImageAttachment> {
  const trimmed = dataUrl.trim();
  if (!DATA_IMAGE_URL_RE.test(trimmed)) {
    throw new Error('unsupported image type');
  }
  if (estimateDataUrlBytes(trimmed) > AGENT_MAX_IMAGE_BYTES) {
    throw new Error('image too large');
  }
  return attachmentFromDataUrl(trimmed, name);
}

export async function createImageAttachmentFromFile(
  file: File,
  mimeHint?: string,
): Promise<AgentChatImageAttachment> {
  const mime = (file.type || mimeHint || '').toLowerCase();
  if (!mime.startsWith('image/')) {
    throw new Error('unsupported image type');
  }
  if (file.size > AGENT_MAX_IMAGE_BYTES) {
    throw new Error('image too large');
  }
  const dataUrl = await readFileAsDataUrl(file);
  return attachmentFromDataUrl(dataUrl, file.name || undefined);
}

export function extractDataImageUrlFromClipboard(
  clipboardData: DataTransfer | null,
): string | null {
  if (!clipboardData) return null;

  const plain = clipboardData.getData('text/plain')?.trim();
  if (plain && DATA_IMAGE_URL_RE.test(plain)) {
    return plain;
  }

  const html = clipboardData.getData('text/html');
  if (html) {
    const match = html.match(/src=["'](data:image\/[^"']+)["']/i);
    if (match?.[1]) {
      return match[1];
    }
  }

  return null;
}

export function collectImageFilesFromClipboard(
  clipboardData: DataTransfer | null,
): Array<{ file: File; mimeHint?: string }> {
  if (!clipboardData) return [];
  const files: Array<{ file: File; mimeHint?: string }> = [];
  const seen = new Set<string>();

  const pushFile = (file: File | null, mimeHint?: string) => {
    if (!file) return;
    const mime = (file.type || mimeHint || '').toLowerCase();
    if (!mime.startsWith('image/')) return;
    const key = `${file.name}:${file.size}:${mime}`;
    if (seen.has(key)) return;
    seen.add(key);
    files.push({ file, mimeHint: mimeHint || file.type || undefined });
  };

  for (const item of Array.from(clipboardData.items)) {
    if (!item.type.startsWith('image/')) continue;
    pushFile(item.getAsFile(), item.type);
  }

  return files;
}

export function mergeImageAttachments(
  current: AgentChatImageAttachment[],
  incoming: AgentChatImageAttachment[],
): AgentChatImageAttachment[] {
  const merged = [...current];
  for (const attachment of incoming) {
    if (merged.length >= AGENT_MAX_IMAGE_ATTACHMENTS) break;
    if (merged.some((item) => item.dataUrl === attachment.dataUrl)) continue;
    merged.push(attachment);
  }
  return merged;
}
