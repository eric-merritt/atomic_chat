import { describe, it, expect } from 'vitest';
import { buildCategory } from '../tool';
import type { Tool } from '../tool';

const makeTool = (name: string, selected: boolean): Tool => ({
  name,
  description: `desc for ${name}`,
  params: {},
  category: 'Test',
  selected,
});

describe('buildCategory', () => {
  it('computes allSelected when all tools selected', () => {
    const cat = buildCategory('Test', [makeTool('a', true), makeTool('b', true)]);
    expect(cat.allSelected).toBe(true);
    expect(cat.someSelected).toBe(true);
    expect(cat.count).toBe(2);
    expect(cat.selectedCount).toBe(2);
  });

  it('computes someSelected when partially selected', () => {
    const cat = buildCategory('Test', [makeTool('a', true), makeTool('b', false)]);
    expect(cat.allSelected).toBe(false);
    expect(cat.someSelected).toBe(true);
    expect(cat.selectedCount).toBe(1);
  });

  it('computes none selected', () => {
    const cat = buildCategory('Test', [makeTool('a', false), makeTool('b', false)]);
    expect(cat.allSelected).toBe(false);
    expect(cat.someSelected).toBe(false);
    expect(cat.selectedCount).toBe(0);
  });

  it('handles empty tools array', () => {
    const cat = buildCategory('Empty', []);
    expect(cat.count).toBe(0);
    expect(cat.allSelected).toBe(true);
    expect(cat.someSelected).toBe(false);
  });
});
