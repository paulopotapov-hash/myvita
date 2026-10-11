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

const longDateFormatter = new Intl.DateTimeFormat('pt-PT', { weekday: 'long', day: 'numeric', month: 'long' })
const timeFormatter = new Intl.DateTimeFormat('pt-PT', { hour: '2-digit', minute: '2-digit' })

/** "terça-feira, 14 de outubro" */
export function formatLongDate(iso: string): string {
  return longDateFormatter.format(new Date(iso))
}

/** "10:30" */
export function formatTime(iso: string): string {
  return timeFormatter.format(new Date(iso))
}
