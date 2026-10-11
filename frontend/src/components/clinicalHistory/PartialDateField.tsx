import { useId, useState } from 'react'
import { precisionOf, type DatePrecision } from '../../lib/partialDate'

interface Props {
  label: string
  /** API form: "2010", "2010-03", "2010-03-12" or "" when empty. */
  value: string
  onChange: (value: string) => void
  error?: string
}

const PRECISION_LABELS: Record<DatePrecision, string> = { year: 'Só o ano', month: 'Mês e ano', day: 'Data completa' }
const INPUT_LABELS: Record<DatePrecision, string> = { year: 'Ano', month: 'Mês', day: 'Data' }

/** A date the patient may only partly remember (decision D5): year, month and year, or the full date. */
export function PartialDateField({ label, value, onChange, error }: Props) {
  const id = useId()
  const [precision, setPrecision] = useState<DatePrecision>(value ? precisionOf(value) : 'year')
  const errorId = `${id}-error`
  const thisYear = new Date().getFullYear()

  function changePrecision(next: DatePrecision) {
    setPrecision(next)
    if (!value) return
    if (next === 'year') onChange(value.slice(0, 4))
    else if (next === 'month') onChange(value.length >= 7 ? value.slice(0, 7) : '')
    else onChange(value.length === 10 ? value : '')
  }

  return (
    <fieldset className="flex flex-col gap-1" aria-describedby={error ? errorId : undefined}>
      <legend className="text-sm font-medium text-slate-700">{label} (opcional)</legend>
      <div className="flex flex-wrap gap-2">
        <label className="sr-only" htmlFor={`${id}-precision`}>{label}: precisão</label>
        <select
          id={`${id}-precision`}
          value={precision}
          onChange={(event) => changePrecision(event.target.value as DatePrecision)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-600"
        >
          {(Object.keys(PRECISION_LABELS) as DatePrecision[]).map((key) => <option key={key} value={key}>{PRECISION_LABELS[key]}</option>)}
        </select>
        <label className="sr-only" htmlFor={`${id}-value`}>{label}: {INPUT_LABELS[precision].toLowerCase()}</label>
        <input
          id={`${id}-value`}
          type={precision === 'year' ? 'number' : precision === 'month' ? 'month' : 'date'}
          inputMode={precision === 'year' ? 'numeric' : undefined}
          min={precision === 'year' ? 1900 : undefined}
          max={precision === 'year' ? thisYear : undefined}
          placeholder={precision === 'year' ? 'AAAA' : precision === 'month' ? 'AAAA-MM' : undefined}
          value={value}
          aria-invalid={Boolean(error)}
          onChange={(event) => onChange(event.target.value)}
          className={`min-w-0 flex-1 rounded-md border px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-600 ${error ? 'border-red-400' : 'border-slate-300'}`}
        />
      </div>
      {error && <p id={errorId} role="alert" className="text-sm text-red-600">{error}</p>}
    </fieldset>
  )
}
