interface Props {
  message: string
  onRetry?: () => void
}

/** Renders a safe, human message — the caller is responsible for having
 * already turned the raw error into one via lib/errorMessages.ts. This
 * component never receives or displays a raw Error/exception itself. */
export function ErrorState({ message, onRetry }: Props) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-6 py-8 text-center text-red-800"
    >
      <p>{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md border border-red-300 bg-white px-4 py-1.5 text-sm font-medium text-red-700 hover:bg-red-100"
        >
          Tentar novamente
        </button>
      )}
    </div>
  )
}
