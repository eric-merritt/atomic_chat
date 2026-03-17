import { describe, it, expect } from 'vitest';
import { parseStreamLine } from '../stream';

describe('parseStreamLine', () => {
  it('parses token event', () => {
    const ev = parseStreamLine({ token: 'hello' });
    expect(ev).toEqual({ type: 'token', token: 'hello' });
  });

  it('parses tool_call event', () => {
    const ev = parseStreamLine({ tool_call: { tool: 'web_search', input: 'test' } });
    expect(ev).toEqual({ type: 'tool_call', tool: 'web_search', input: 'test' });
  });

  it('parses tool_result event', () => {
    const ev = parseStreamLine({ tool_result: { tool: 'web_search', output: 'results' } });
    expect(ev).toEqual({ type: 'tool_result', tool: 'web_search', output: 'results' });
  });

  it('parses image event with snake_case to camelCase', () => {
    const ev = parseStreamLine({ image: { src: '/img.jpg', filename: 'img.jpg', size_kb: 42 } });
    expect(ev).toEqual({ type: 'image', src: '/img.jpg', filename: 'img.jpg', sizeKb: 42 });
  });

  it('parses error event', () => {
    const ev = parseStreamLine({ error: 'something broke' });
    expect(ev).toEqual({ type: 'error', message: 'something broke' });
  });

  it('returns null for unknown shape', () => {
    const ev = parseStreamLine({ unknown: true });
    expect(ev).toBeNull();
  });
});
