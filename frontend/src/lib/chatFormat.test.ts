import { describe, expect, it } from 'vitest'
import { chatTime, dayKey, daySeparatorLabel, listTime, shortDate } from './chatFormat'

// Local-time fixtures: built with the Date constructor so the test is timezone-independent.
const now = new Date(2026, 9, 11, 15, 30) // Sunday 11 Oct 2026, 15:30
const at = (month: number, day: number, hour = 9, minute = 5, year = 2026) => new Date(year, month, day, hour, minute).toISOString()

describe('chatFormat', () => {
  it('shows the time inside bubbles', () => {
    expect(chatTime(at(9, 11, 20, 0))).toBe('20:00')
    expect(chatTime(at(9, 11, 8, 7))).toBe('08:07')
  })

  it('labels day separators Hoje, Ontem, then a short date', () => {
    expect(daySeparatorLabel(at(9, 11, 0, 1), now)).toBe('Hoje')
    expect(daySeparatorLabel(at(9, 10, 23, 59), now)).toBe('Ontem')
    expect(daySeparatorLabel(at(9, 9), now)).toBe('9 out')
    expect(daySeparatorLabel(at(11, 31, 9, 0, 2025), now)).toBe('31 dez 2025')
    expect(shortDate(at(0, 2), now)).toBe('2 jan')
  })

  it('formats conversation list times like a messaging app', () => {
    expect(listTime(at(9, 11, 14, 0), now)).toBe('14:00')
    expect(listTime(at(9, 10), now)).toBe('Ontem')
    expect(listTime(at(9, 7), now)).toBe('quarta')
    expect(listTime(at(8, 20), now)).toBe('20 set')
  })

  it('groups messages by local day', () => {
    expect(dayKey(at(9, 11, 0, 1))).toBe(dayKey(at(9, 11, 23, 59)))
    expect(dayKey(at(9, 11))).not.toBe(dayKey(at(9, 10)))
  })
})
