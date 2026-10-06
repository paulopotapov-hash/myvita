interface Props {
  kind: 'error' | 'success'
  children: React.ReactNode
  className?: string
}

/** Form-level feedback: errors are announced as alerts, successes as status. */
export function FormMessage({ kind, children, className = '' }: Props) {
  const isError = kind === 'error'
  return (
    <p role={isError ? 'alert' : 'status'} className={`text-sm ${isError ? 'text-red-600' : 'text-teal-700'} ${className}`}>
      {children}
    </p>
  )
}
