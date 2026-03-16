import { describe, it, expect } from 'vitest';
import { createMessage, createMessageFromHistory } from '../message';

describe('createMessage', () => {
  it('creates a user message with generated id', () => {
    const m = createMessage('user', 'hello');
    expect(m.id).toBeTruthy();
    expect(m.role).toBe('user');
    expect(m.content).toBe('hello');
    expect(m.images).toEqual([]);
    expect(m.toolCalls).toEqual([]);
    expect(m.timestamp).toBeGreaterThan(0);
  });

  it('creates an error message', () => {
    const m = createMessage('error', 'something broke');
    expect(m.role).toBe('error');
  });
});

describe('createMessageFromHistory', () => {
  it('constructs Message from backend history entry', () => {
    const m = createMessageFromHistory({ role: 'assistant', content: 'hi' });
    expect(m.id).toBeTruthy();
    expect(m.role).toBe('assistant');
    expect(m.content).toBe('hi');
    expect(m.images).toEqual([]);
    expect(m.toolCalls).toEqual([]);
    expect(m.timestamp).toBe(0);
  });
});
