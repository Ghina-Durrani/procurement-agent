import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PolicyOutcomeBadge } from './PolicyOutcomeBadge'

describe('PolicyOutcomeBadge', () => {
  it.each([
    ['CONTINUE', 'Continue'],
    ['BLOCK', 'Blocked'],
    ['HUMAN_REVIEW', 'Human review'],
  ] as const)('shows a readable label for %s', (outcome, label) => {
    render(<PolicyOutcomeBadge outcome={outcome} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })
})
