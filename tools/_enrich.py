"""LLM enrichment loop and @enrichable decorator for tool classes."""

import json
import re

import json5

from tools._output import tool_result


def enrich_data(data: str, goal: str, max_iterations: int = 5, eval_model: str = 'qwen3:4b') -> dict:
    """Iteratively enrich data toward a goal using an LLM eval loop.

    Returns a tool_result dict with enriched_data, iteration_log, and exit_reason.
    """
    if not data or not data.strip():
        return tool_result(error="Empty data input.")

    try:
        from config import OLLAMA_NUM_CTX
        from qwen_agent.llm import get_chat_model
        llm = get_chat_model({
            'model': f'ollama/{eval_model}',
            'model_server': 'http://localhost:11434/v1',
            'api_key': 'ollama',
            'generate_cfg': {'temperature': 0, 'max_input_tokens': OLLAMA_NUM_CTX},
        })
    except Exception as e:
        return tool_result(error=f"Failed to initialize eval model '{eval_model}': {e}. Run: ollama pull {eval_model}")

    system_prompt = """You are a data enrichment engine. Your job is to iteratively add new dimensions/considerations to data until the goal is fully satisfied.

Respond ONLY with valid JSON (no markdown fences, no explanation outside JSON).

If there are more dimensions to add, respond with:
{"action": "enrich", "dimension": "short_name", "description": "what you added and why", "enriched_data": <the full data with the new dimension merged in>}

If the goal is fully satisfied, respond with:
{"action": "done", "reasoning": "why all requested dimensions are complete"}"""

    current_data = data
    iteration_log = []
    consecutive_failures = 0

    for iteration in range(1, max_iterations + 1):
        display_data = current_data
        if len(current_data) > 4000:
            display_data = current_data[:4000]
            iteration_log.append({
                "iteration": iteration,
                "warning": f"Data truncated from {len(current_data)} to 4000 chars for eval model",
            })

        log_summary = "None yet" if not iteration_log else json.dumps(
            [e for e in iteration_log if "dimension" in e], indent=2
        )

        user_prompt = f"""GOAL: {goal}

CURRENT DATA:
{display_data}

PREVIOUS ITERATIONS:
{log_summary}

Iteration {iteration} of {max_iterations}. Add the next enrichment dimension, or signal done."""

        response_text = ""
        try:
            messages = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ]
            response_list = []
            for chunk in llm.chat(messages=messages, stream=False):
                response_list = chunk
            response_text = (response_list[-1] if response_list else {}).get('content', '').strip()

            fence_match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", response_text, re.DOTALL)
            if fence_match:
                response_text = fence_match.group(1).strip()

            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            consecutive_failures += 1
            iteration_log.append({"iteration": iteration, "error": "Malformed JSON", "raw": response_text[:200]})
            if consecutive_failures >= 2:
                break
            continue
        except Exception as e:
            consecutive_failures += 1
            iteration_log.append({"iteration": iteration, "error": f"LLM call failed: {e}"})
            if consecutive_failures >= 2:
                break
            continue

        consecutive_failures = 0
        action = parsed.get("action", "")

        if action == "done":
            iteration_log.append({"iteration": iteration, "action": "done", "reasoning": parsed.get("reasoning", "")})
            break
        elif action == "enrich":
            enriched = parsed.get("enriched_data")
            if enriched is not None:
                current_data = json.dumps(enriched, indent=2) if not isinstance(enriched, str) else enriched
            iteration_log.append({
                "iteration": iteration,
                "action": "enrich",
                "dimension": parsed.get("dimension", "unknown"),
                "description": parsed.get("description", ""),
            })
        else:
            consecutive_failures += 1
            iteration_log.append({"iteration": iteration, "error": f"Unknown action '{action}'"})
            if consecutive_failures >= 2:
                break

    if consecutive_failures >= 2:
        exit_reason = "consecutive_failures"
    elif iteration_log and iteration_log[-1].get("action") == "done":
        exit_reason = "llm_done"
    else:
        exit_reason = "max_iterations"

    try:
        final_data = json.loads(current_data)
    except (json.JSONDecodeError, TypeError):
        final_data = current_data

    return tool_result(data={
        "iterations_used": len([e for e in iteration_log if e.get("action") in ("enrich", "done") or "error" in e]),
        "max_iterations": max_iterations,
        "exit_reason": exit_reason,
        "iteration_log": iteration_log,
        "enriched_data": final_data,
    })


_ENRICH_PARAMS = {
    'enrich_goal':       {'type': 'string',  'description': 'If set, pipe tool output through an LLM enrichment loop toward this goal.'},
    'enrich_iterations': {'type': 'integer', 'description': 'Max enrichment iterations. Default: 5.'},
    'enrich_model':      {'type': 'string',  'description': 'Ollama model for enrichment. Default: qwen3:4b.'},
}


def enrichable(cls):
    """Class decorator that adds optional LLM enrichment to any BaseTool.

    Injects enrich_goal / enrich_iterations / enrich_model into the tool's
    parameters, then wraps call() to pipe the result through enrich_data()
    when enrich_goal is provided.

    Usage:
        @register_tool('my_tool')
        @enrichable
        class MyTool(BaseTool):
            ...
    """
    cls.parameters['properties'].update(_ENRICH_PARAMS)

    original_call = cls.call

    def call(self, params: str, **kwargs) -> dict:
        result = original_call(self, params, **kwargs)
        if result.get('error'):
            return result
        p = json5.loads(params)
        goal = p.get('enrich_goal', '')
        if not goal:
            return result
        return enrich_data(
            data=json.dumps(result.get('data', result)),
            goal=goal,
            max_iterations=p.get('enrich_iterations', 5),
            eval_model=p.get('enrich_model', 'qwen3:4b'),
        )

    cls.call = call
    return cls
