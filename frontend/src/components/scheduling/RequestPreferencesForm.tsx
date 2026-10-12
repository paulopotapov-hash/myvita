import { useState } from 'react'
import { addDays, clinicToday, WEEKDAYS } from '../../lib/clinicTime'
import type { AppointmentRequestCreate, RequestPeriod } from '../../types/api'
import { Button } from '../Button'
import { FormMessage } from '../FormMessage'
import { TextAreaField } from '../TextAreaField'
import { TextField } from '../TextField'

export type RequestPreferences = Pick<
  AppointmentRequestCreate,
  'preferred_from' | 'preferred_to' | 'preferred_weekdays' | 'preferred_period' | 'reason'
>

interface Props {
  /** Last day the clinic accepts (its booking horizon), "YYYY-MM-DD". */
  maxDate?: string
  submitLabel: string
  isPending: boolean
  error?: string
  /** Ask for the reason (not when moving an appointment that already has one). */
  withReason?: boolean
  onSubmit: (preferences: RequestPreferences) => void
}

/**
 * "Só por pedido": the patient says when suits them (dates, weekdays, morning or
 * afternoon) and the clinic confirms or proposes a time. The server re-checks everything.
 */
export function RequestPreferencesForm({ maxDate, submitLabel, isPending, error, withReason = true, onSubmit }: Props) {
  const today = clinicToday()
  const [from, setFrom] = useState(() => addDays(today, 1))
  const [to, setTo] = useState(() => addDays(today, 14))
  const [weekdays, setWeekdays] = useState<number[]>([])
  const [period, setPeriod] = useState<RequestPeriod | ''>('')
  const [reason, setReason] = useState('')
  const [formError, setFormError] = useState('')

  function submit(event: React.FormEvent) {
    event.preventDefault()
    setFormError('')
    if (!from) return setFormError('Indica a partir de quando preferes a consulta.')
    if (from < today) return setFormError('Escolhe datas a partir de hoje.')
    if (to && to < from) return setFormError('A data final tem de ser igual ou posterior à inicial.')
    if (maxDate && (to || from) > maxDate) return setFormError('Escolhe datas dentro do período em que a clínica marca consultas.')
    onSubmit({
      preferred_from: from,
      ...(to ? { preferred_to: to } : {}),
      ...(weekdays.length ? { preferred_weekdays: weekdays } : {}),
      ...(period ? { preferred_period: period } : {}),
      ...(withReason && reason.trim() ? { reason: reason.trim() } : {}),
    })
  }

  return (
    <form noValidate onSubmit={submit} aria-label="Preferências para a consulta" className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label="A partir de" type="date" value={from} min={today} max={maxDate} onChange={(event) => setFrom(event.target.value)} />
        <TextField label="Até (opcional)" type="date" value={to} min={from || today} max={maxDate} onChange={(event) => setTo(event.target.value)} />
      </div>
      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-slate-700">Dias da semana (opcional)</legend>
        <div className="flex flex-wrap gap-2">
          {WEEKDAYS.map((label, day) => (
            <label key={label} className="flex min-h-11 items-center gap-2 rounded-md border border-slate-200 px-3 text-sm">
              <input
                type="checkbox"
                checked={weekdays.includes(day)}
                onChange={(event) =>
                  setWeekdays((current) => (event.target.checked ? [...current, day].sort() : current.filter((item) => item !== day)))
                }
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-slate-700">Período do dia</legend>
        <div className="flex flex-wrap gap-2">
          {([['', 'Indiferente'], ['morning', 'Manhã'], ['afternoon', 'Tarde']] as Array<[RequestPeriod | '', string]>).map(([value, label]) => (
            <label key={label} className="flex min-h-11 items-center gap-2 rounded-md border border-slate-200 px-3 text-sm">
              <input type="radio" name="preferred-period" checked={period === value} onChange={() => setPeriod(value)} />
              {label}
            </label>
          ))}
        </div>
      </fieldset>
      {withReason && <TextAreaField label="Motivo da consulta (opcional)" value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} />}
      {(formError || error) && <FormMessage kind="error">{formError || error}</FormMessage>}
      <Button type="submit" isLoading={isPending}>{submitLabel}</Button>
    </form>
  )
}
