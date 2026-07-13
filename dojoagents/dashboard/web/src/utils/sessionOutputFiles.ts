export interface SessionOutputFileInfo {
  filename: string;
  path: string;
  bytes_written?: number;
  output_dir?: string;
}

function parseSessionOutputEntry(value: unknown): SessionOutputFileInfo | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  const record = value as Record<string, unknown>;
  const path = typeof record.path === 'string' ? record.path.trim() : '';
  const filename = typeof record.filename === 'string' ? record.filename.trim() : '';
  if (!path || !filename) {
    return null;
  }
  return {
    filename,
    path,
    bytes_written: typeof record.bytes_written === 'number' ? record.bytes_written : undefined,
    output_dir: typeof record.output_dir === 'string' ? record.output_dir : undefined,
  };
}

export function parseSessionOutputFilesFromToolData(
  tool: string,
  data?: Record<string, unknown> | null,
): SessionOutputFileInfo[] {
  if (!data) {
    return [];
  }

  if (tool === 'write_session_file') {
    const single = parseSessionOutputEntry(data);
    return single ? [single] : [];
  }

  if (tool === 'execute_code' || tool === 'code_execution') {
    const files = Array.isArray(data.session_output_files) ? data.session_output_files : [];
    const parsed = files
      .map((item) => parseSessionOutputEntry(item))
      .filter((item): item is SessionOutputFileInfo => item !== null);
    if (parsed.length > 0) {
      return parsed;
    }
    const single = parseSessionOutputEntry(data);
    return single ? [single] : [];
  }

  return [];
}

export function parseSessionOutputFileFromToolData(
  tool: string,
  data?: Record<string, unknown> | null,
): SessionOutputFileInfo | null {
  const files = parseSessionOutputFilesFromToolData(tool, data);
  return files.length > 0 ? files[files.length - 1] : null;
}

export function formatBytesLabel(bytes: number, locale: 'zh' | 'en'): string {
  if (bytes < 1024) {
    return locale === 'zh' ? `${bytes} 字节` : `${bytes} B`;
  }
  const kb = bytes / 1024;
  if (kb < 1024) {
    return locale === 'zh' ? `${kb.toFixed(1)} KB` : `${kb.toFixed(1)} KB`;
  }
  const mb = kb / 1024;
  return locale === 'zh' ? `${mb.toFixed(1)} MB` : `${mb.toFixed(1)} MB`;
}
