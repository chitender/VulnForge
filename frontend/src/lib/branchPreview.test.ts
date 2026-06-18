import { describe, expect, it } from 'vitest'
import { resolveBranchPreview } from './branchPreview'

describe('resolveBranchPreview', () => {
  it('substitutes known variables', () => {
    const result = resolveBranchPreview('hotfix/{image}-{date}', {
      image: 'payments-api',
      date: '2026-06-18',
    })
    expect(result).toBe('hotfix/payments-api-2026-06-18')
  })

  it('replaces slashes with hyphens in image slug', () => {
    const result = resolveBranchPreview('feature/{image}', {
      image: 'myorg/payments/api',
    })
    expect(result).toBe('feature/myorg-payments-api')
  })

  it('leaves unknown variables as-is', () => {
    const result = resolveBranchPreview('{unknown}-fix', {})
    expect(result).toBe('{unknown}-fix')
  })

  it('returns empty string for empty template', () => {
    expect(resolveBranchPreview('   ', {})).toBe('')
  })

  it('substitutes multiple occurrences', () => {
    const result = resolveBranchPreview('{image}-{image}', { image: 'app' })
    expect(result).toBe('app-app')
  })
})
