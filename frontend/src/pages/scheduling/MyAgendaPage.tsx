import { useState } from 'react'
import { Button } from '../../components/Button'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { ErrorState } from '../../components/ErrorState'
import { FormMessage } from '../../components/FormMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { SelectField } from '../../components/SelectField'
import { TextField } from '../../components/TextField'
import { useAgenda, useSchedulingChange } from '../../hooks/useScheduling'
import {
  addDays,
  clinicDateKey,
  clinicLocalToIso,
  clinicToday,
  formatClinicDate,
  formatClinicTime,
  mondayOf,
  WEEKDAYS,
} from '../../lib/clinicTime'
import { toUserMessage } from '../../lib/errorMessages'
import type { Absence, AbsenceKind } from '../../types/scheduling'

const STATUS_LABELS: Record<string, string> = {
  scheduled: 'Marcada',
  confirmed: 'Confirmada',
  completed: 'Realizada',
  cancelled: 'Cancelada',
  no_show: 'Faltou',
}
const KIND_LABELS: Record<AbsenceKind, string> = { vacation: 'Férias', other: 'Indisponível' }

/** A professional's own week: appointments and absences, and blocking new absences. */
export function MyAgendaPage() {
  const [monday, setMonday] = useState(() => mondayOf(clinicToday()))
  const sunday = addDays(monday, 6)
  const agenda = useAgenda(monday, sunday)
  const change = useSchedulingChange()
  const [form, setForm] = useState({ starts: '', ends: '', kind: 'vacation' as AbsenceKind })
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [removing, setRemoving] = useState<Absence | null>(null)

  function addAbsence(event: React.FormEvent) {
    event.preventDefault()
    setFeedback(null)
    if (!form.starts || !form.ends || form.ends <= form.starts) {
      setFeedback({ kind: 'error', text: 'Indica o início e um fim posterior ao início.' })
      return
    }
    change.mutate(
      { kind: 'addAbsence', payload: { starts_at: clinicLocalToIso(form.starts), ends_at: clinicLocalToIso(form.ends), kind: form.kind } },
      {
        onSuccess: (created) => {
          const conflicts = (created as Absence).conflicting_appointments
          setForm({ starts: '', ends: '', kind: 'vacation' })
          setFeedback({
            kind: 'success',
            text: conflicts > 0
              ? `Ausência registada. Há ${conflicts} consulta(s) marcada(s) nesse período: a clínica tem de as remarcar.`
              : 'Ausência registada.',
          })
        },
        onError: (error) => setFeedback({ kind: 'error', text: toUserMessage(error) }),
      },
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">A minha agenda</h1>
        <p className="text-sm text-slate-500">Consultas e ausências da semana (hora de Lisboa).</p>
      </div>

      <nav aria-label="Semana" className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" onClick={() => setMonday(addDays(monday, -7))}>Semana anterior</Button>
        <p className="text-sm font-medium text-slate-700" aria-live="polite">
          {formatClinicDate(`${monday}T12:00:00Z`)} a {formatClinicDate(`${sunday}T12:00:00Z`)}
        </p>
        <Button variant="secondary" onClick={() => setMonday(addDays(monday, 7))}>Semana seguinte</Button>
      </nav>

      {agenda.isLoading && <LoadingSpinner label="A carregar a agenda…" />}
      {agenda.isError && <ErrorState message={toUserMessage(agenda.error)} onRetry={() => agenda.refetch()} />}
      {agenda.data && (
        <ol className="grid gap-3 lg:grid-cols-2">
          {WEEKDAYS.map((label, index) => {
            const day = addDays(monday, index)
            const appointments = agenda.data.appointments.filter((item) => clinicDateKey(item.scheduled_at) === day)
            const absences = agenda.data.absences.filter((item) => clinicDateKey(item.starts_at) <= day && clinicDateKey(item.ends_at) >= day)
            return (
              <li key={day} className="rounded-xl border border-slate-200 bg-white p-4">
                <h2 className="text-base font-semibold text-slate-900">{label} <span className="font-normal text-slate-500">{formatClinicDate(`${day}T12:00:00Z`)}</span></h2>
                {appointments.length === 0 && absences.length === 0 && <p className="mt-1 text-sm text-slate-500">Sem consultas.</p>}
                <ul className="mt-2 flex flex-col gap-2">
                  {absences.map((absence) => (
                    <li key={absence.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-amber-50 px-3 py-2 text-sm">
                      <span id={`absence-${absence.id}-${day}`}>
                        {KIND_LABELS[absence.kind]}: {formatClinicDate(absence.starts_at)} {formatClinicTime(absence.starts_at)} – {formatClinicDate(absence.ends_at)} {formatClinicTime(absence.ends_at)}
                      </span>
                      <Button variant="secondary" aria-describedby={`absence-${absence.id}-${day}`} onClick={() => setRemoving(absence)}>Remover ausência</Button>
                    </li>
                  ))}
                  {appointments.map((item) => (
                    <li key={item.id} className="rounded-md border border-slate-100 px-3 py-2 text-sm">
                      <span className="font-medium">{formatClinicTime(item.scheduled_at)}–{formatClinicTime(item.ends_at)}</span> · {item.patient_name} · {item.appointment_type}
                      <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs">{STATUS_LABELS[item.status] ?? item.status}</span>
                      {item.patient_confirmed && <span className="ml-2 rounded-full bg-teal-50 px-2 py-0.5 text-xs text-teal-900">Presença confirmada</span>}
                    </li>
                  ))}
                </ul>
              </li>
            )
          })}
        </ol>
      )}

      <section aria-labelledby="absence-title" className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 id="absence-title" className="mb-4 text-lg font-medium">Bloquear ausência</h2>
        <form className="grid gap-3 sm:grid-cols-4" onSubmit={addAbsence} noValidate>
          <TextField label="Início" type="datetime-local" required value={form.starts} onChange={(event) => setForm({ ...form, starts: event.target.value })} />
          <TextField label="Fim" type="datetime-local" required value={form.ends} onChange={(event) => setForm({ ...form, ends: event.target.value })} />
          <SelectField label="Motivo" value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as AbsenceKind })}>
            <option value="vacation">Férias</option>
            <option value="other">Indisponível</option>
          </SelectField>
          <div className="self-end"><Button type="submit" isLoading={change.isPending}>Bloquear</Button></div>
        </form>
        {feedback && <FormMessage kind={feedback.kind} className="mt-3">{feedback.text}</FormMessage>}
      </section>

      {removing && (
        <ConfirmDialog
          title="Remover ausência"
          description="O período volta a ficar disponível para marcações."
          confirmLabel="Remover"
          isPending={change.isPending}
          onCancel={() => setRemoving(null)}
          onConfirm={() =>
            change.mutate({ kind: 'deleteAbsence', id: removing.id }, {
              onSuccess: () => { setRemoving(null); setFeedback({ kind: 'success', text: 'Ausência removida.' }) },
              onError: (error) => { setRemoving(null); setFeedback({ kind: 'error', text: toUserMessage(error) }) },
            })
          }
        />
      )}
    </div>
  )
}
