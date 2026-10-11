/** "Hoje" / "Ontem" / "9 out" between days in a conversation. */
export function DateSeparator({ label }: { label: string }) {
  return (
    <li className="flex justify-center py-1">
      <span className="rounded-full bg-white px-3 py-1 text-sm font-medium text-slate-600 shadow-sm ring-1 ring-slate-100">{label}</span>
    </li>
  )
}
