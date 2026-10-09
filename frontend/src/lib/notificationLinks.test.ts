import { describe, expect, it } from 'vitest'
import { notificationLink } from './notificationLinks'
import type { NotificationPublic } from '../types/api'

function notification(overrides: Partial<NotificationPublic> = {}): NotificationPublic {
  return {
    id: 'n1',
    title: 'Aviso',
    message: 'Genérica',
    is_read: false,
    read_at: null,
    created_at: '2026-10-01T09:00:00Z',
    target_type: null,
    target_id: null,
    conversation_target_id: null,
    ...overrides,
  }
}

describe('notificationLink', () => {
  it('opens the specific conversation for patients and staff', () => {
    const target = notification({ title: 'Nova mensagem', target_type: 'conversation', conversation_target_id: 'conv-1' })
    expect(notificationLink(target, { role: 'patient' })).toEqual({ to: '/patient/mensagens/conv-1', label: 'Abrir conversa' })
    expect(notificationLink(target, { role: 'staff' })).toEqual({ to: '/app/mensagens/conv-1', label: 'Abrir conversa' })
  })

  it('opens the patient documents with the document highlighted', () => {
    const target = notification({ title: 'Novo documento', target_type: 'document', target_id: 'doc-1' })
    expect(notificationLink(target, { role: 'patient' })).toEqual({ to: '/patient/documentos?document=doc-1', label: 'Abrir documento' })
  })

  it('encodes target ids into the URL', () => {
    const target = notification({ target_type: 'conversation', conversation_target_id: 'a/b?c' })
    expect(notificationLink(target, { role: 'patient' }).to).toBe('/patient/mensagens/a%2Fb%3Fc')
  })

  it('keeps the inbox link for message notifications created before deep links existed', () => {
    expect(notificationLink(notification({ title: 'Nova mensagem' }), { role: 'staff' })).toEqual({ to: '/app/mensagens', label: 'Abrir mensagens' })
  })

  it('falls back to appointments for untargeted notifications', () => {
    expect(notificationLink(notification(), { role: 'patient' }).to).toBe('/patient/consultas')
    expect(notificationLink(notification(), { role: 'clinic_admin' }).to).toBe('/app/consultas')
    expect(notificationLink(notification(), null).to).toBe('/app/consultas')
  })
})
