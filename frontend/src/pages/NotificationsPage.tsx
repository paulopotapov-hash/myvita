import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useSession } from '../hooks/useSession'
import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { useMarkNotificationRead, useNotifications } from '../hooks/useClinicalData'
import { toUserMessage } from '../lib/errorMessages'
import { formatDateTime } from '../lib/formatDate'

export function NotificationsPage() {
  const [page, setPage] = useState(1)
  const [actionError, setActionError] = useState('')
  const { user } = useSession()
  const pageSize = 20
  const notifications = useNotifications(page, pageSize)
  const markRead = useMarkNotificationRead()
  const total = notifications.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Notificações</h1>
        {notifications.data && <p className="rounded-full bg-teal-50 px-3 py-1 text-sm font-medium text-teal-800" aria-label={`${notifications.data.items.filter((item) => !item.is_read).length} não lidas nesta página`}>
          {notifications.data.items.filter((item) => !item.is_read).length} não lidas nesta página
        </p>}
      </div>
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        {actionError && <p role="alert" className="mb-3 text-sm text-red-700">{actionError}</p>}
        {notifications.isLoading && <LoadingSpinner />}
        {notifications.isError && <ErrorState message={toUserMessage(notifications.error)} onRetry={() => notifications.refetch()} />}
        {notifications.data?.items.length === 0 && <EmptyState title="Sem notificações" description="Não existem notificações para mostrar." />}
        {notifications.data && notifications.data.items.length > 0 && <ul className="divide-y divide-slate-100">{notifications.data.items.map((notification) => <li key={notification.id} className={`flex flex-wrap items-start justify-between gap-3 py-4 ${notification.is_read ? 'opacity-70' : ''}`}><div><div className="flex flex-wrap items-center gap-2"><p className="font-medium">{notification.title}</p>{!notification.is_read && <span className="rounded-full bg-teal-100 px-2 py-0.5 text-xs text-teal-800">Nova</span>}</div><p className="text-sm text-slate-600">{notification.message}</p><p className="mt-1 text-xs text-slate-500">{formatDateTime(notification.created_at)}</p><Link to={user?.role === 'patient' ? '/patient/consultas' : '/app/consultas'} className="mt-2 inline-block text-xs font-medium text-teal-700 hover:underline">Abrir consultas</Link></div>{!notification.is_read && <Button variant="secondary" isLoading={markRead.isPending && markRead.variables === notification.id} onClick={() => { setActionError(''); markRead.mutate(notification.id, { onError: (error) => setActionError(toUserMessage(error)) }) }}>Marcar como lida</Button>}</li>)}</ul>}
        {notifications.data && total > pageSize && <div className="mt-5 flex items-center justify-between gap-3"><Button variant="secondary" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Anterior</Button><span className="text-sm text-slate-500">Página {page} de {pages}</span><Button variant="secondary" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>Seguinte</Button></div>}
      </section>
    </div>
  )
}
