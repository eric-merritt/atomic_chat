# Enrichment Pipeline Tool Design

## Summary

A single `@tool` function `enrichment_pipeline` that iteratively enriches data using a small dedicated eval model (qwen3:4b). The agent calls it once with input data and a goal; internally it loops up to 5 times, with the eval model deciding each iteration whether to add another dimension or stop.

## Signature

```python
@tool
def enrichment_pipeline(
    data: str,
    goal: str,
    max_iterations: int = 5,
    eval_model: str = "qwen3:4b",
) -> str:
```

## Loop Mechanics

Each iteration sends the eval model:
1. The enrichment goal
2. Current data state
3. Log of what previous iterations added

Eval model responds with JSON:
- `{"action": "enrich", "dimension": "...", "description": "...", "enriched_data": {...}}` to continue
- `{"action": "done", "reasoning": "..."}` to stop

## Return Value

```json
{
  "status": "completed",
  "iterations_used": 3,
  "max_iterations": 5,
  "exit_reason": "llm_done | max_iterations | consecutive_failures",
  "iteration_log": [...],
  "enriched_data": { ... }
}
```

## Edge Cases

- Data too large: truncate to ~4000 chars, log warning
- Eval model not pulled: return error with `ollama pull` instruction
- Malformed JSON: skip iteration, 2 consecutive failures → exit early
- Empty data: return error immediately

## Integration

- Added to `ALL_TOOLS` in `tools.py`
- Documented in system prompt in `main.py`
- No changes to agent loop or Flask routes
