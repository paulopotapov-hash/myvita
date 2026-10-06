interface Props {
  title: string
  description?: string
  action?: React.ReactNode
}

export function EmptyState({ title, description, action }: Props) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-slate-300 px-6 py-12 text-center text-slate-500">
      <p className="font-medium text-slate-700">{title}</p>
      {description && <p className="text-sm">{description}</p>}
      {action}
    </div>
  )
}
