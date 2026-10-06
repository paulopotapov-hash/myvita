import { useMutation } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { toUserMessage } from '../lib/errorMessages'
import { mfaCodeSchema } from '../lib/validation'
import { authService } from '../services/auth'
import { Button } from './Button'
import { TextField } from './TextField'
import { useFocusFirstInvalid } from '../hooks/useFocusFirstInvalid'

/**
 * TOTP enrolment: start setup (the seed is shown exactly once), confirm with
 * a first code, then show the one-time recovery codes. `onDone` runs after
 * the user confirms they stored the recovery codes.
 */
export function MfaEnrolment({ onDone }: { onDone: () => void }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const formRef = useFocusFirstInvalid(useMemo<Record<string, string>>(() => Object.fromEntries(error ? [['code', error]] : []), [error]))
  const setup = useMutation({ mutationFn: () => authService.startMfaSetup() })
  const enable = useMutation({ mutationFn: (code: string) => authService.enableMfa(code) })

  if (enable.data) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm text-slate-700">
          Autenticação de dois fatores ativa. Guarda estes códigos de recuperação num local seguro: cada um
          funciona uma única vez se perderes o dispositivo, e não voltam a ser mostrados.
        </p>
        <ul aria-label="Códigos de recuperação" className="grid grid-cols-2 gap-2 rounded-md bg-slate-50 p-3 font-mono text-sm">
          {enable.data.recovery_codes.map((recovery) => (
            <li key={recovery}>{recovery}</li>
          ))}
        </ul>
        <Button onClick={onDone}>Guardei os códigos — continuar</Button>
      </div>
    )
  }

  if (!setup.data) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-slate-700">
          Vais precisar de uma aplicação autenticadora (por exemplo, Microsoft Authenticator, Google Authenticator
          ou Aegis).
        </p>
        {setup.isError && <p role="alert" className="text-sm text-red-600">{toUserMessage(setup.error)}</p>}
        <Button onClick={() => setup.mutate()} isLoading={setup.isPending}>
          Configurar autenticação de dois fatores
        </Button>
      </div>
    )
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (enable.isPending) return
    const parsed = mfaCodeSchema.safeParse(code)
    if (!parsed.success) {
      setError(parsed.error.issues[0].message)
      return
    }
    setError(null)
    enable.mutate(parsed.data, {
      onError: (failure) => {
        setCode('')
        setError(toUserMessage(failure))
      },
    })
  }

  return (
    <form ref={formRef} onSubmit={submit} noValidate className="flex flex-col gap-4">
      <p className="text-sm text-slate-700">
        Na aplicação autenticadora, adiciona uma conta com esta chave (ou abre a ligação neste dispositivo):
      </p>
      <p aria-label="Chave secreta" className="break-all rounded-md bg-slate-50 p-3 font-mono text-sm tracking-wider">
        {setup.data.secret}
      </p>
      <a href={setup.data.otpauth_uri} className="text-sm font-medium text-teal-700 underline">
        Abrir na aplicação autenticadora
      </a>
      <TextField
        label="Código de 6 dígitos"
        required
        inputMode="numeric"
        autoComplete="one-time-code"
        value={code}
        onChange={(e) => setCode(e.target.value)}
        error={error ?? undefined}
      />
      <Button type="submit" isLoading={enable.isPending}>
        Ativar
      </Button>
    </form>
  )
}
