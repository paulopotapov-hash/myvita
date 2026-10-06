import { useState } from 'react'
import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { useMarkNotificationRead, useNotifications } from '../hooks/useClinicalData'
import { toUserMessage } from '../lib/errorMessages'
import { formatDateTime } from '../lib/formatDate'

export function NotificationsPage() {
  const [page, setPage] = useState(1)
  const pageSize = 20
  const notifications = useNotifications(page, pageSize)
  const markRead = useMarkNotificationRead()
  const total = notifications.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Notificações</h1>
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        {notifications.isLoading && <LoadingSpinner />}
        {notifications.isError && <ErrorState message={toUserMessage(notifications.error)} onRetry={() => notifications.refetch()} />}
        {notifications.data?.items.length === 0 && <EmptyState title="Sem notificações" description="Não existem notificações para mostrar." />}
        {notifications.data && notifications.data.items.length > 0 && <ul className="divide-y divide-slate-100">{notifications.data.items.map((notification) => <li key={notification.id} className={`flex flex-wrap items-start justify-between gap-3 py-4 ${notification.is_read ? 'opacity-70' : ''}`}><div><div className="flex items-center gap-2"><p className="font-medium">{notification.title}</p>{!notification.is_read && <span className="rounded-full bg-teal-100 px-2 py-0.5 text-xs text-teal-800">Nova</span>}</div><p className="text-sm text-slate-600">{notification.message}</p><p className="mt-1 text-xs text-slate-500">{formatDateTime(notification.created_at)}</p></div>{!notification.is_read && <Button variant="secondary" isLoading={markRead.isPending} onClick={() => markRead.mutate(notification.id)}>Marcar como lida</Button>}</li>)}</ul>}
        {total > pageSize && <div className="mt-5 flex items-center justify-between"><Button variant="secondary" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Anterior</Button><span className="text-sm text-slate-500">Página {page} de {pages}</span><Button variant="secondary" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>Seguinte</Button></div>}
      </section>
    </div>
  )
}
