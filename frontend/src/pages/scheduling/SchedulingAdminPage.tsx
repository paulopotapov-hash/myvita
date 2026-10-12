import { useState } from 'react'
import { Button } from '../../components/Button'
import { ErrorState } from '../../components/ErrorState'
import { FormMessage } from '../../components/FormMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { SelectField } from '../../components/SelectField'
import { TextField } from '../../components/TextField'
import {
  useAppointmentTypes,
  useBookingSettings,
  useProfessionals,
  useSchedule,
  useSchedulingChange,
  useSpecialties,
  type SchedulingChange,
} from '../../hooks/useScheduling'
import { WEEKDAYS } from '../../lib/clinicTime'
import { toUserMessage } from '../../lib/errorMessages'
import type { BookingMode, BookingSettings, ScheduleRule } from '../../types/scheduling'

const MODE_LABELS: Record<BookingMode, string> = { direct: 'Marcação direta', request: 'Só por pedido' }

type Feedback = { kind: 'success' | 'error'; text: string } | null

function useChange() {
  const change = useSchedulingChange()
  const [feedback, setFeedback] = useState<Feedback>(null)
  function run(variables: SchedulingChange, success: string, after?: () => void) {
    setFeedback(null)
    change.mutate(variables, {
      onSuccess: () => {
        setFeedback({ kind: 'success', text: success })
        after?.()
      },
      onError: (error) => setFeedback({ kind: 'error', text: toUserMessage(error) }),
    })
  }
  return { run, feedback, isPending: change.isPending }
}

function Card({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="rounded-xl border border-slate-200 bg-white p-6">
      <h2 id={id} className="mb-4 text-lg font-medium text-slate-900">{title}</h2>
      {children}
    </section>
  )
}

/** Clinic administrators and administrative staff: booking configuration and agendas. */
export function SchedulingAdminPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Agendas e marcações</h1>
        <p className="text-sm text-slate-500">Tipos de consulta, especialidades, regras da clínica e a agenda semanal de cada profissional. As horas são de Lisboa.</p>
      </div>
      <SettingsCard />
      <SpecialtiesCard />
      <TypesCard />
      <ProfessionalsCard />
    </div>
  )
}

function SettingsCard() {
  const settings = useBookingSettings()
  return (
    <Card id="settings-title" title="Regras da clínica">
      {settings.isLoading && <LoadingSpinner />}
      {settings.isError && <ErrorState message={toUserMessage(settings.error)} onRetry={() => settings.refetch()} />}
      {settings.data && (
        <SettingsForm
          initial={{
            cancellation_deadline_hours: settings.data.cancellation_deadline_hours,
            waitlist_offer_minutes: settings.data.waitlist_offer_minutes,
            reminder_hours_before: settings.data.reminder_hours_before,
            booking_horizon_days: settings.data.booking_horizon_days,
          }}
        />
      )}
    </Card>
  )
}

function SettingsForm({ initial }: { initial: BookingSettings }) {
  const { run, feedback, isPending } = useChange()
  const [form, setForm] = useState<BookingSettings>(initial)
  const fields: Array<[keyof BookingSettings, string]> = [
    ['cancellation_deadline_hours', 'Prazo para cancelar ou remarcar na app (horas antes)'],
    ['waitlist_offer_minutes', 'Validade de uma vaga da lista de espera (minutos)'],
    ['reminder_hours_before', 'Lembrete enviado (horas antes)'],
    ['booking_horizon_days', 'Marcações até (dias à frente)'],
  ]
  return (
    <form
      className="grid gap-4 sm:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault()
        run({ kind: 'settings', payload: form }, 'Regras guardadas.')
      }}
    >
      {fields.map(([key, label]) => (
        <TextField key={key} label={label} type="number" min={0} required value={String(form[key])} onChange={(event) => setForm({ ...form, [key]: Number(event.target.value) })} />
      ))}
      <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
        <Button type="submit" isLoading={isPending}>Guardar regras</Button>
        {feedback && <FormMessage kind={feedback.kind}>{feedback.text}</FormMessage>}
      </div>
    </form>
  )
}

function SpecialtiesCard() {
  const specialties = useSpecialties()
  const { run, feedback, isPending } = useChange()
  const [name, setName] = useState('')
  return (
    <Card id="specialties-title" title="Especialidades">
      {specialties.isError && <ErrorState message={toUserMessage(specialties.error)} onRetry={() => specialties.refetch()} />}
      <ul className="mb-4 divide-y divide-slate-100">
        {(specialties.data ?? []).map((specialty) => (
          <li key={specialty.id} className="flex items-center justify-between gap-3 py-2">
            <span id={`specialty-${specialty.id}`} className={specialty.active ? '' : 'text-slate-400 line-through'}>{specialty.name}</span>
            <Button variant="secondary" aria-describedby={`specialty-${specialty.id}`} disabled={isPending} onClick={() => run({ kind: 'updateSpecialty', id: specialty.id, payload: { active: !specialty.active } }, 'Especialidade atualizada.')}>
              {specialty.active ? 'Desativar' : 'Ativar'}
            </Button>
          </li>
        ))}
      </ul>
      <form className="flex flex-wrap items-end gap-3" onSubmit={(event) => { event.preventDefault(); if (name.trim()) run({ kind: 'createSpecialty', name: name.trim() }, 'Especialidade criada.', () => setName('')) }}>
        <TextField label="Nova especialidade" value={name} maxLength={120} onChange={(event) => setName(event.target.value)} />
        <Button type="submit" isLoading={isPending}>Adicionar especialidade</Button>
      </form>
      {feedback && <FormMessage kind={feedback.kind} className="mt-3">{feedback.text}</FormMessage>}
    </Card>
  )
}

function TypesCard() {
  const types = useAppointmentTypes()
  const specialties = useSpecialties()
  const { run, feedback, isPending } = useChange()
  const empty = { name: '', duration_minutes: '30', specialty_id: '', booking_mode: 'direct' as BookingMode }
  const [form, setForm] = useState(empty)
  const specialtyName = new Map((specialties.data ?? []).map((specialty) => [specialty.id, specialty.name]))
  return (
    <Card id="types-title" title="Tipos de consulta">
      {types.isError && <ErrorState message={toUserMessage(types.error)} onRetry={() => types.refetch()} />}
      {(types.data ?? []).length > 0 && (
        <table className="mb-4 w-full text-left text-sm">
          <thead className="text-slate-500"><tr><th className="py-2">Nome</th><th>Duração</th><th>Especialidade</th><th>Modo</th><th>Estado</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {(types.data ?? []).map((type) => (
              <tr key={type.id}>
                <td className="py-2 font-medium">{type.name}</td>
                <td>{type.duration_minutes} min</td>
                <td>{specialtyName.get(type.specialty_id) ?? '—'}</td>
                <td>
                  <label className="sr-only" htmlFor={`mode-${type.id}`}>Modo de {type.name}</label>
                  <select id={`mode-${type.id}`} className="rounded-md border border-slate-300 px-2 py-1" value={type.booking_mode} disabled={isPending}
                    onChange={(event) => run({ kind: 'updateType', id: type.id, payload: { booking_mode: event.target.value as BookingMode } }, 'Tipo de consulta atualizado.')}>
                    {(Object.keys(MODE_LABELS) as BookingMode[]).map((mode) => <option key={mode} value={mode}>{MODE_LABELS[mode]}</option>)}
                  </select>
                </td>
                <td>
                  <Button variant="secondary" aria-label={`${type.active ? 'Desativar' : 'Ativar'} ${type.name}`} disabled={isPending}
                    onClick={() => run({ kind: 'updateType', id: type.id, payload: { active: !type.active } }, 'Tipo de consulta atualizado.')}>
                    {type.active ? 'Desativar' : 'Ativar'}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form
        aria-label="Novo tipo de consulta"
        className="grid gap-3 sm:grid-cols-4"
        onSubmit={(event) => {
          event.preventDefault()
          if (!form.name.trim() || !form.specialty_id) return
          run(
            { kind: 'createType', payload: { name: form.name.trim(), duration_minutes: Number(form.duration_minutes), specialty_id: form.specialty_id, booking_mode: form.booking_mode } },
            'Tipo de consulta criado.',
            () => setForm(empty),
          )
        }}
      >
        <TextField label="Nome do tipo" required value={form.name} maxLength={120} onChange={(event) => setForm({ ...form, name: event.target.value })} />
        <TextField label="Duração (minutos)" type="number" min={5} max={480} required value={form.duration_minutes} onChange={(event) => setForm({ ...form, duration_minutes: event.target.value })} />
        <SelectField label="Especialidade" required value={form.specialty_id} onChange={(event) => setForm({ ...form, specialty_id: event.target.value })}>
          <option value="">Escolhe…</option>
          {(specialties.data ?? []).filter((specialty) => specialty.active).map((specialty) => <option key={specialty.id} value={specialty.id}>{specialty.name}</option>)}
        </SelectField>
        <SelectField label="Modo de marcação" value={form.booking_mode} onChange={(event) => setForm({ ...form, booking_mode: event.target.value as BookingMode })}>
          {(Object.keys(MODE_LABELS) as BookingMode[]).map((mode) => <option key={mode} value={mode}>{MODE_LABELS[mode]}</option>)}
        </SelectField>
        <div className="sm:col-span-4"><Button type="submit" isLoading={isPending}>Adicionar tipo de consulta</Button></div>
      </form>
      {feedback && <FormMessage kind={feedback.kind} className="mt-3">{feedback.text}</FormMessage>}
    </Card>
  )
}

function ProfessionalsCard() {
  const professionals = useProfessionals()
  const [selected, setSelected] = useState('')
  const professional = (professionals.data ?? []).find((item) => item.id === selected)
  return (
    <Card id="professionals-title" title="Profissionais e agenda semanal">
      {professionals.isError && <ErrorState message={toUserMessage(professionals.error)} onRetry={() => professionals.refetch()} />}
      <SelectField label="Profissional" value={selected} onChange={(event) => setSelected(event.target.value)}>
        <option value="">Escolhe…</option>
        {(professionals.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.full_name}</option>)}
      </SelectField>
      {professional && <ProfessionalEditor key={professional.id} staffId={professional.id} specialtyId={professional.specialty_id} acceptsNew={professional.accepts_new_patients} />}
    </Card>
  )
}

function ProfessionalEditor({ staffId, specialtyId, acceptsNew }: { staffId: string; specialtyId: string | null; acceptsNew: boolean }) {
  const specialties = useSpecialties()
  const types = useAppointmentTypes()
  const schedule = useSchedule(staffId)
  const profile = useChange()
  const [specialty, setSpecialty] = useState(specialtyId ?? '')
  const [accepts, setAccepts] = useState(acceptsNew)
  const allowedTypes = (types.data ?? []).filter((type) => type.specialty_id === specialtyId && type.active)

  return (
    <div className="mt-5 flex flex-col gap-6">
      <form
        aria-label="Perfil de marcação"
        className="flex flex-wrap items-end gap-4"
        onSubmit={(event) => {
          event.preventDefault()
          profile.run({ kind: 'professional', id: staffId, payload: { specialty_id: specialty || null, accepts_new_patients: accepts } }, 'Perfil guardado.')
        }}
      >
        <SelectField label="Especialidade do profissional" value={specialty} onChange={(event) => setSpecialty(event.target.value)}>
          <option value="">Sem especialidade</option>
          {(specialties.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </SelectField>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={accepts} onChange={(event) => setAccepts(event.target.checked)} />
          Aceita pacientes novos
        </label>
        <Button type="submit" isLoading={profile.isPending}>Guardar perfil</Button>
        {profile.feedback && <FormMessage kind={profile.feedback.kind}>{profile.feedback.text}</FormMessage>}
      </form>

      {schedule.isLoading && <LoadingSpinner />}
      {schedule.isError && <ErrorState message={toUserMessage(schedule.error)} onRetry={() => schedule.refetch()} />}
      {schedule.data && (
        // Initialised once per professional (the editor is keyed by them): a refetch after
        // saving must not reset the form or hide the confirmation.
        <WeeklyScheduleForm
          staffId={staffId}
          hasSpecialty={Boolean(specialtyId)}
          allowedTypes={allowedTypes}
          initial={schedule.data.map((rule) => ({ ...rule, start_time: rule.start_time.slice(0, 5), end_time: rule.end_time.slice(0, 5) }))}
        />
      )}
    </div>
  )
}

function WeeklyScheduleForm({ staffId, hasSpecialty, allowedTypes, initial }: {
  staffId: string
  hasSpecialty: boolean
  allowedTypes: Array<{ id: string; name: string }>
  initial: ScheduleRule[]
}) {
  const saveSchedule = useChange()
  const [rules, setRules] = useState<ScheduleRule[]>(initial)
  function setRule(index: number, patch: Partial<ScheduleRule>) {
    setRules((current) => current.map((rule, position) => (position === index ? { ...rule, ...patch } : rule)))
  }
  return (
      <form
        aria-label="Agenda semanal"
        onSubmit={(event) => {
          event.preventDefault()
          saveSchedule.run({ kind: 'schedule', staffId, rules }, 'Agenda semanal guardada.')
        }}
      >
        <h3 className="mb-2 text-sm font-semibold text-slate-700">Agenda semanal</h3>
        {!hasSpecialty && <p className="mb-2 text-sm text-slate-500">Guarda primeiro a especialidade do profissional para escolher os tipos de consulta.</p>}
        <ul className="flex flex-col gap-3">
          {rules.map((rule, index) => (
            <li key={index} className="grid gap-3 rounded-lg border border-slate-200 p-3 sm:grid-cols-[10rem_7rem_7rem_1fr_auto]">
              <SelectField label="Dia" value={String(rule.weekday)} onChange={(event) => setRule(index, { weekday: Number(event.target.value) })}>
                {WEEKDAYS.map((day, weekday) => <option key={day} value={weekday}>{day}</option>)}
              </SelectField>
              <TextField label="Início" type="time" required value={rule.start_time} onChange={(event) => setRule(index, { start_time: event.target.value })} />
              <TextField label="Fim" type="time" required value={rule.end_time} onChange={(event) => setRule(index, { end_time: event.target.value })} />
              <fieldset className="flex flex-col gap-1">
                <legend className="text-sm font-medium text-slate-700">Tipos de consulta</legend>
                {allowedTypes.map((type) => (
                  <label key={type.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={rule.appointment_type_ids.includes(type.id)}
                      onChange={(event) => setRule(index, {
                        appointment_type_ids: event.target.checked
                          ? [...rule.appointment_type_ids, type.id]
                          : rule.appointment_type_ids.filter((id) => id !== type.id),
                      })}
                    />
                    {type.name}
                  </label>
                ))}
              </fieldset>
              <div className="self-end"><Button variant="secondary" onClick={() => setRules((current) => current.filter((_, position) => position !== index))}>Remover bloco</Button></div>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button variant="secondary" onClick={() => setRules((current) => [...current, { weekday: 0, start_time: '09:00', end_time: '12:00', valid_from: null, valid_until: null, appointment_type_ids: allowedTypes.map((type) => type.id) }])}>
            Adicionar bloco
          </Button>
          <Button type="submit" isLoading={saveSchedule.isPending}>Guardar agenda semanal</Button>
          {saveSchedule.feedback && <FormMessage kind={saveSchedule.feedback.kind}>{saveSchedule.feedback.text}</FormMessage>}
        </div>
      </form>
  )
}
