import { originLabel } from '../../lib/clinicalHistoryLabels'

/** "Confirmado pelo profissional" / "Declarado pelo paciente", plus "Oculto ao paciente" for the team. */
export function EntryBadges({ confirmed, hidden = false }: { confirmed: boolean; hidden?: boolean }) {
  return (
    <span className="flex flex-wrap gap-1.5">
      <span
        className={`rounded-full px-2 py-0.5 text-xs font-medium ${confirmed ? 'bg-teal-50 text-teal-800' : 'bg-amber-50 text-amber-900'}`}
      >
        {originLabel({ confirmed })}
      </span>
      {hidden && <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs font-medium text-white">Oculto ao paciente</span>}
    </span>
  )
}
