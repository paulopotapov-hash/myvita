import { describe, expect, it } from 'vitest'
import { formatPartialDate, precisionOf } from './partialDate'

describe('partial dates', () => {
  it('shows each precision the way it was entered', () => {
    expect(formatPartialDate('2010')).toBe('2010')
    expect(formatPartialDate('2010-03')).toBe('março 2010')
    expect(formatPartialDate('2010-03-12')).toBe('12/03/2010')
    expect(formatPartialDate(null)).toBeNull()
  })

  it('reads the precision from the API form', () => {
    expect(precisionOf('2010')).toBe('year')
    expect(precisionOf('2010-03')).toBe('month')
    expect(precisionOf('2010-03-12')).toBe('day')
  })
})
