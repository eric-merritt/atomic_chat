import { describe, it, expect } from 'vitest';
import { modelId, parseModelString } from '../model';

describe('modelId', () => {
  it('builds id with devTeam', () => {
    expect(modelId({
      devTeam: 'huihui_ai',
      name: 'qwen2.5-coder-abliterate',
      numParams: '14b',
      available: true,
      format: null, maker: null, year: null, description: null,
      goodAt: null, notSoGoodAt: null, idealUseCases: null, contextWindow: null,
    })).toBe('huihui_ai/qwen2.5-coder-abliterate:14b');
  });

  it('builds id without devTeam', () => {
    expect(modelId({
      devTeam: null,
      name: 'llama3.1',
      numParams: '8b',
      available: true,
      format: null, maker: null, year: null, description: null,
      goodAt: null, notSoGoodAt: null, idealUseCases: null, contextWindow: null,
    })).toBe('llama3.1:8b');
  });
});

describe('parseModelString', () => {
  it('parses devTeam/name:params', () => {
    const m = parseModelString('huihui_ai/qwen2.5-coder-abliterate:14b');
    expect(m.devTeam).toBe('huihui_ai');
    expect(m.name).toBe('qwen2.5-coder-abliterate');
    expect(m.numParams).toBe('14b');
    expect(m.available).toBe(true);
  });

  it('parses name:params without devTeam', () => {
    const m = parseModelString('llama3.1:8b');
    expect(m.devTeam).toBeNull();
    expect(m.name).toBe('llama3.1');
    expect(m.numParams).toBe('8b');
  });

  it('sets all metadata to null', () => {
    const m = parseModelString('llama3.1:8b');
    expect(m.format).toBeNull();
    expect(m.maker).toBeNull();
    expect(m.year).toBeNull();
    expect(m.description).toBeNull();
    expect(m.goodAt).toBeNull();
    expect(m.notSoGoodAt).toBeNull();
    expect(m.idealUseCases).toBeNull();
    expect(m.contextWindow).toBeNull();
  });
});
