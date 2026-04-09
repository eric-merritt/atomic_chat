// frontend/src/lib/__tests__/toolAdapters.test.ts
import { getAdapter } from '../toolAdapters'

test('fs_grep summarize', () => {
  const a = getAdapter('fs_grep')!
  const data = { pattern: 'config', count: 14, matches: [
    { file: '/src/a.py', line: 1, snippet: '  >     1  x' },
    { file: '/src/b.py', line: 5, snippet: '  >     5  y' },
  ], truncated: false }
  expect(a.summarize({}, data)).toBe("Found 14 matches for 'config' across 2 files")
})

test('fs_grep toHierarchy groups by file', () => {
  const a = getAdapter('fs_grep')!
  const data = { pattern: 'config', count: 2, matches: [
    { file: '/src/a.py', line: 3, snippet: '  >     3  x = config()' },
    { file: '/src/a.py', line: 7, snippet: '  >     7  y = config()' },
    { file: '/src/b.py', line: 1, snippet: '  >     1  import config' },
  ], truncated: false }
  const nodes = a.toHierarchy({}, data)
  expect(nodes[0]).toMatchObject({ label: '/src/a.py', depth: 0, isFile: true, href: '/src/a.py' })
  expect(nodes[1]).toMatchObject({ label: 'line 3: x = config()', depth: 1, isFile: false })
  expect(nodes[2]).toMatchObject({ label: 'line 7: y = config()', depth: 1, isFile: false })
  expect(nodes[3]).toMatchObject({ label: '/src/b.py', depth: 0, isFile: true })
})

test('fs_find summarize', () => {
  const a = getAdapter('fs_find')!
  const data = { path: '/src', count: 8, files: ['/src/a.py'] }
  expect(a.summarize({}, data)).toBe('Found 8 files in /src')
})

test('fs_find toHierarchy flat file list', () => {
  const a = getAdapter('fs_find')!
  const data = { path: '/src', count: 2, files: ['/src/a.py', '/src/b.py'] }
  const nodes = a.toHierarchy({}, data)
  expect(nodes).toHaveLength(2)
  expect(nodes[0]).toMatchObject({ label: '/src/a.py', depth: 0, isFile: true, href: '/src/a.py' })
})

test('www_ddg summarize', () => {
  const a = getAdapter('www_ddg')!
  const data = { abstract: '', abstract_url: '', results: [{text:'a',url:'http://x.com'},{text:'b',url:'http://y.com'}] }
  expect(a.summarize({ query: 'python config' }, data)).toBe('Web search: 2 results')
})

test('www_ddg toHierarchy builds external links', () => {
  const a = getAdapter('www_ddg')!
  const data = { abstract: '', abstract_url: '', results: [
    { text: 'How to configure Python', url: 'https://docs.python.org/config' },
  ]}
  const nodes = a.toHierarchy({ query: 'python config' }, data)
  expect(nodes[0]).toMatchObject({ label: 'python config — 1 results', depth: 0, isFile: false })
  expect(nodes[1]).toMatchObject({ isExternal: true, depth: 0, href: 'https://docs.python.org/config' })
  expect(nodes[2]).toMatchObject({ label: 'How to configure Python', depth: 1, isFile: false })
})

test('www_fetch summarize', () => {
  const a = getAdapter('www_fetch')!
  const data = { ref: 'abc123', url: 'https://example.com', title: 'Example', size_chars: 45000 }
  expect(a.summarize({}, data)).toBe('Fetched example.com — ref abc123, 45000 chars')
})

test('www_get summarize', () => {
  const a = getAdapter('www_get')!
  const data = { ref: 'abc123', url: 'https://x.com', selector: '.price', count: 12, results: [] }
  expect(a.summarize({}, data)).toBe("12 elements matching '.price'")
})

test('fs_tree toHierarchy parses lsd tree output into nodes', () => {
  const a = getAdapter('fs_tree')!
  // lsd --tree output format: 4-char prefix per depth level using box-drawing chars
  // Directories are marked with trailing slash
  const tree = [
    'src/',
    '├── components/',
    '│   └── atoms/',
    '│       └── Button.tsx',
    '└── hooks/',
    '    └── useStream.ts',
  ].join('\n')
  const nodes = a.toHierarchy({}, { path: '/home/ermer/project', tree })
  // Root dir
  expect(nodes[0]).toMatchObject({ label: 'src', depth: 0, isFile: false })
  // components dir
  expect(nodes[1]).toMatchObject({ label: 'components', depth: 1, isFile: false })
  // atoms dir
  expect(nodes[2]).toMatchObject({ label: 'atoms', depth: 2, isFile: false })
  // Button.tsx file — isFile true, href reconstructed from root + path
  expect(nodes[3]).toMatchObject({ label: 'Button.tsx', depth: 3, isFile: true })
  expect(nodes[3].href).toContain('Button.tsx')
  // hooks dir
  expect(nodes[4]).toMatchObject({ label: 'hooks', depth: 1, isFile: false })
  // useStream.ts file
  expect(nodes[5]).toMatchObject({ label: 'useStream.ts', depth: 2, isFile: true })
  expect(nodes[5].href).toContain('useStream.ts')
})

test('getAdapter returns null for unknown tool', () => {
  expect(getAdapter('unknown_tool')).toBeNull()
})
