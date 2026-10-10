import { describe, expect, it } from 'vitest'
import { emailDeliveryNotice } from './emailDelivery'

describe('emailDeliveryNotice', () => {
  it('never claims an email went out unless the relay accepted it', () => {
    expect(emailDeliveryNotice('sent')).toMatch(/^Enviámos/)
    expect(emailDeliveryNotice('failed')).toMatch(/Não foi possível enviar/)
    expect(emailDeliveryNotice('disabled')).toMatch(/não está configurado/)
    expect(emailDeliveryNotice('failed')).not.toMatch(/Enviámos/)
    expect(emailDeliveryNotice('disabled')).not.toMatch(/Enviámos/)
  })
})
