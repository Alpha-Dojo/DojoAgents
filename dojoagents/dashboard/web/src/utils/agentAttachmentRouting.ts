import { AGENT_UPLOAD_ACCEPT } from './agentFileAttachments';

export const AGENT_ATTACHMENT_ACCEPT = `image/*,${AGENT_UPLOAD_ACCEPT}`;

export const AGENT_ATTACHMENT_COLLAPSE_THRESHOLD = 4;

export function isImageAttachmentFile(file: File): boolean {
  const mime = (file.type || '').toLowerCase();
  if (mime.startsWith('image/')) {
    return true;
  }
  const name = file.name.toLowerCase();
  return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(name);
}

export function collectFilesFromDataTransfer(
  dataTransfer: DataTransfer | null,
): File[] {
  if (!dataTransfer) return [];
  const files: File[] = [];
  const seen = new Set<string>();
  for (const item of Array.from(dataTransfer.items)) {
    if (item.kind !== 'file') continue;
    const file = item.getAsFile();
    if (!file) continue;
    const key = `${file.name}:${file.size}:${file.type}`;
    if (seen.has(key)) continue;
    seen.add(key);
    files.push(file);
  }
  if (files.length > 0) {
    return files;
  }
  return Array.from(dataTransfer.files ?? []);
}

export function partitionAttachmentFiles(files: File[]): {
  images: File[];
  documents: File[];
} {
  const images: File[] = [];
  const documents: File[] = [];
  for (const file of files) {
    if (isImageAttachmentFile(file)) {
      images.push(file);
    } else {
      documents.push(file);
    }
  }
  return { images, documents };
}

export function attachmentKindIcon(kind: string): string {
  switch (kind) {
    case 'excel':
      return '📊';
    case 'pdf':
      return '📄';
    case 'csv':
      return '🧾';
    case 'code':
      return '💻';
    case 'json':
    case 'jsonl':
      return '{ }';
    default:
      return '📎';
  }
}
