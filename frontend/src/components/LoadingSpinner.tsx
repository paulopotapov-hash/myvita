interface Props {
  label?: string
}

export function LoadingSpinner({ label = 'A carregar…' }: Props) {
  return (
    <div className="flex items-center justify-center gap-3 py-10 text-slate-500" role="status">
      <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
        />
      </svg>
      <span>{label}</span>
    </div>
  )
}
