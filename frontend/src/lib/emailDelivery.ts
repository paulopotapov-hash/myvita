import type { EmailDelivery } from '../types/api'

/**
 * What happened to the e-mail carrying a one-time link (backend app/core/email.py).
 * "sent" only means the mail relay accepted it, so the link stays available as a fallback.
 */
export function emailDeliveryNotice(delivery: EmailDelivery): string {
  if (delivery === 'sent') return 'Enviámos o link por email. Se a pessoa não o receber, partilhe-o por um canal seguro.'
  if (delivery === 'failed') return 'Não foi possível enviar o email. Partilhe o link diretamente com a pessoa, por um canal seguro.'
  return 'O envio de email não está configurado. Partilhe o link diretamente com a pessoa, por um canal seguro.'
}
