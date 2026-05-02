"""Token counting via llama-server /tokenize endpoint with Qwen chat template rendering."""

import json
import logging
import os
import threading
from typing import Optional

_log = logging.getLogger(__name__)

# Approximate tokens added per tool definition (name + description + parameter schema).
# Measured empirically; actual varies by tool complexity.
TOKENS_PER_TOOL = 350


def _render_qwen_template(messages: list[dict]) -> str:
    """Format messages in Qwen3.5 chat template so /tokenize counts template tokens too."""
    parts = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "unknown")
        content = msg.get("content") or ""

        if isinstance(content, list):
            content = " ".join(
                str(b.get("text") or b.get("content", "")) if isinstance(b, dict) else str(b)
                for b in content
            )
        content = str(content)

        # function_call data sits outside `content` in qwen-agent message dicts
        fn_call = msg.get("function_call")
        if fn_call:
            fc_str = json.dumps(fn_call) if isinstance(fn_call, dict) else str(fn_call)
            content = f"{content}\n{fc_str}" if content else fc_str

        parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")

    parts.append("<|im_start|>assistant\n")
    return "\n".join(parts)


def _tokenize_via_server(text: str) -> Optional[int]:
    """Call running llama-server /tokenize — the exact tokenizer the model uses."""
    try:
        import requests as _req
        from config import LLAMA_SERVER_URL
        resp = _req.post(
            f"{LLAMA_SERVER_URL}/tokenize",
            json={"content": text, "add_special": True},
            timeout=5,
        )
        if resp.ok:
            return len(resp.json().get("tokens", []))
        _log.debug("llama-server /tokenize returned HTTP %s", resp.status_code)
    except Exception as e:
        _log.debug("llama-server /tokenize unavailable: %s", e)
    return None


def _get_model_path() -> Optional[str]:
    from config import DEFAULT_MODEL, MODELS
    model_name = os.environ.get("DEFAULT_MODEL", DEFAULT_MODEL)
    cfg = MODELS.get(model_name, {})
    return cfg.get("path") or os.environ.get("LLAMA_DEFAULT_MODEL")


class TokenCounter:
    """Tokenizer-only wrapper — vocab_only fallback when server is unreachable."""

    def __init__(self, model_path: str = None):
        self.model_path = model_path or _get_model_path()
        self._model = None
        self._init_model()

    def _init_model(self):
        if self.model_path and os.path.exists(self.model_path):
            try:
                from llama_cpp import Llama
                self._model = Llama(
                    model_path=self.model_path,
                    vocab_only=True,
                    n_gpu_layers=0,
                    n_ctx=512,
                    verbose=False,
                )
            except Exception as e:
                _log.warning("TokenCounter vocab-only init failed: %s", e)

    def _tokenize_raw(self, text: str) -> int:
        if self._model:
            return len(self._model.tokenize(text.encode("utf-8"), add_bos=False))
        return len(text) // 4

    def count_tokens_from_messages(self, messages: list[dict]) -> int:
        rendered = _render_qwen_template(messages)
        server = _tokenize_via_server(rendered)
        if server is not None:
            return server
        return self._tokenize_raw(rendered)

    def count_tokens(self, text: str) -> int:
        server = _tokenize_via_server(text)
        if server is not None:
            return server
        return self._tokenize_raw(text)


_counter: Optional[TokenCounter] = None
_counter_lock = threading.Lock()


def _get_counter() -> TokenCounter:
    global _counter
    if _counter is None:
        with _counter_lock:
            if _counter is None:
                _counter = TokenCounter()
    return _counter


def count_tokens(messages: list[dict]) -> int:
    return _get_counter().count_tokens_from_messages(messages)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def estimate_context_usage(messages: list[dict], max_ctx: int = None) -> float:
    if max_ctx is None:
        from config import LLAMA_ARG_CTX_SIZE
        max_ctx = LLAMA_ARG_CTX_SIZE
    return min(count_tokens(messages) / max_ctx, 1.0)
