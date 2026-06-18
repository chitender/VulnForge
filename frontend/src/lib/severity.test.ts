import { describe, expect, it } from 'vitest'
import { SEVERITY_COLORS, SEVERITY_ORDER } from './severity'

describe('severity constants', () => {
  it('defines colors for all severity levels', () => {
    for (const level of SEVERITY_ORDER) {
      expect(SEVERITY_COLORS[level]).toMatch(/^#[0-9a-f]{6}$/i)
    }
  })

  it('severity order is CRITICAL first, UNKNOWN last', () => {
    expect(SEVERITY_ORDER[0]).toBe('CRITICAL')
    expect(SEVERITY_ORDER[SEVERITY_ORDER.length - 1]).toBe('UNKNOWN')
  })

  it('has exactly 5 severity levels', () => {
    expect(SEVERITY_ORDER).toHaveLength(5)
  })
})
