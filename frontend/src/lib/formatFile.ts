export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function fileTypeLabel(contentType: string): string {
  switch (contentType) {
    case 'application/pdf': return 'PDF'
    case 'image/png': return 'PNG'
    case 'image/jpeg': return 'JPEG'
    default: return 'Ficheiro'
  }
}
