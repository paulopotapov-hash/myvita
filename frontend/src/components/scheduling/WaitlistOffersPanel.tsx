import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAcceptOffer, useWaitlist, useWaitlistChange } from '../../hooks/useWaitlist'
import { formatClinicDay, formatClinicTime } from '../../lib/clinicTime'
import { toUserMessage } from '../../lib/errorMessages'
import { Button } from '../Button'
import { FormMessage } from '../FormMessage'

/** Earlier slots offered from the waiting list: whoever accepts first gets it. */
export function WaitlistOffersPanel() {
  const navigate = useNavigate()
  const waitlist = useWaitlist()
  const accept = useAcceptOffer()
  const change = useWaitlistChange()
  const [error, setError] = useState('')
  const offers = (waitlist.data ?? []).flatMap((entry) => entry.offers)
  if (offers.length === 0) return null

  return (
    <section aria-labelledby="offers-heading" className="flex flex-col gap-3 rounded-xl border border-teal-200 bg-teal-50 p-4">
      <h2 id="offers-heading" className="text-lg font-semibold text-teal-950">Vagas mais cedo</h2>
      <p className="text-sm text-teal-900">Abriu uma vaga antes da tua consulta. Quem aceitar primeiro fica com ela; a consulta atual é cancelada.</p>
      {error && <FormMessage kind="error">{error}</FormMessage>}
      <ul className="flex flex-col gap-3" aria-label="Vagas oferecidas">
        {offers.map((offer) => (
          <li key={offer.id} className="flex flex-col gap-2 rounded-lg bg-white p-3">
            <p className="font-medium text-slate-900">
              <span className="first-letter:uppercase">{formatClinicDay(offer.starts_at)}</span>, {formatClinicTime(offer.starts_at)} · {offer.staff_name}
            </p>
            <p className="text-sm text-slate-600">Válida até às {formatClinicTime(offer.expires_at)}</p>
            <div className="flex flex-wrap gap-2">
              <Button
                isLoading={accept.isPending && accept.variables === offer.id}
                onClick={() => {
                  setError('')
                  accept.mutate(offer.id, {
                    onSuccess: (moved) => navigate(`/patient/consultas/${moved.id}`, { state: { fromWaitlist: true } }),
                    onError: (failure) => setError(toUserMessage(failure)),
                  })
                }}
              >
                Aceitar vaga
              </Button>
              <Button
                variant="secondary"
                isLoading={change.isPending}
                onClick={() => {
                  setError('')
                  change.mutate({ kind: 'decline', offerId: offer.id }, { onError: (failure) => setError(toUserMessage(failure)) })
                }}
              >
                Recusar
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
