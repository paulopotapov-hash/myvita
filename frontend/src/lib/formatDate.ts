const dateTimeFormatter = new Intl.DateTimeFormat('pt-PT', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

const dateFormatter = new Intl.DateTimeFormat('pt-PT', { dateStyle: 'medium' })

export function formatDateTime(iso: string): string {
  return dateTimeFormatter.format(new Date(iso))
}

export function formatDate(iso: string): string {
  return dateFormatter.format(new Date(iso))
}
