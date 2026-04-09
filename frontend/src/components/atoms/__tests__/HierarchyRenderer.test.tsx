import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { HierarchyRenderer } from '../HierarchyRenderer'
import type { HierarchyNode } from '../HierarchyRenderer'

const nodes: HierarchyNode[] = [
  { label: '/src/config.py', depth: 0, isFile: true, href: '/src/config.py' },
  { label: 'line 14: x = 1', depth: 1, isFile: false },
  { label: 'Stack Overflow | stackoverflow.com', depth: 0, isFile: false, isExternal: true, href: 'https://stackoverflow.com' },
]

describe('HierarchyRenderer', () => {
  it('renders all labels', () => {
    render(<HierarchyRenderer nodes={nodes} onFileClick={() => {}} />)
    expect(screen.getByText(/line 14: x = 1/)).toBeInTheDocument()
    expect(screen.getByText('/src/config.py')).toBeInTheDocument()
  })

  it('file node calls onFileClick with href', async () => {
    const onClick = vi.fn()
    render(<HierarchyRenderer nodes={nodes} onFileClick={onClick} />)
    await userEvent.click(screen.getByText('/src/config.py'))
    expect(onClick).toHaveBeenCalledWith('/src/config.py')
  })

  it('external node renders as anchor with target blank', () => {
    render(<HierarchyRenderer nodes={nodes} onFileClick={() => {}} />)
    const link = screen.getByText(/Stack Overflow/)
    expect(link.tagName).toBe('A')
    expect(link).toHaveAttribute('href', 'https://stackoverflow.com')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })
})
