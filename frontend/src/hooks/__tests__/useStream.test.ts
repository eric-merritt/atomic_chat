import { describe, it, expect } from 'vitest';
import { parseNdjsonLines } from '../useStream';

describe('parseNdjsonLines', () => {
  it('splits complete lines and returns remainder', () => {
    const { events, remainder } = parseNdjsonLines('{"token":"a"}\n{"token":"b"}\n');
    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({ type: 'token', token: 'a' });
    expect(events[1]).toEqual({ type: 'token', token: 'b' });
    expect(remainder).toBe('');
  });

  it('buffers incomplete line', () => {
    const { events, remainder } = parseNdjsonLines('{"token":"a"}\n{"tok');
    expect(events).toHaveLength(1);
    expect(remainder).toBe('{"tok');
  });

  it('handles empty string', () => {
    const { events, remainder } = parseNdjsonLines('');
    expect(events).toHaveLength(0);
    expect(remainder).toBe('');
  });

  it('skips empty lines', () => {
    const { events, remainder } = parseNdjsonLines('\n\n{"token":"a"}\n\n');
    expect(events).toHaveLength(1);
    expect(remainder).toBe('');
  });
});
