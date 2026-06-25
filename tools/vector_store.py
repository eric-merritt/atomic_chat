"""Vector store tools: semantic storage and retrieval via ChromaDB + sentence-transformers."""

import os
import sys

# Project root on sys.path so `from tools.x` / `from config` resolve no matter
# how this file is launched (by path, as a module, or from inside tools/).
ROOT = os.path.expanduser("~") + "/devproj/python/atomic_chat"
if ROOT not in sys.path:
  sys.path.insert(0, ROOT)


import json
from pathlib import Path

from qwen_agent.tools.base import BaseTool, register_tool

from tools._output import tool_result

_DB_PATH = os.environ.get(
  "VECTOR_DB_PATH",
  str(Path.home() / ".atomic_chat" / "vector_db"),
)
_EMBED_MODEL = os.environ.get("VECTOR_EMBED_MODEL", "BAAI/bge-small-en-v1.5")

_client = None
_ef = None


def _get_client():
  global _client, _ef
  if _client is None:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    Path(_DB_PATH).mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=_DB_PATH)
    _ef = SentenceTransformerEmbeddingFunction(model_name=_EMBED_MODEL)
  return _client, _ef


def _collection(name: str):
  client, ef = _get_client()
  return client.get_or_create_collection(name=name, embedding_function=ef)


@register_tool('kb_store')
class KnowledgeStore(BaseTool):
  description = (
    'Store text in the persistent vector database for later semantic retrieval. '
    'Use this to remember facts, documents, or any information the agent should recall.'
  )
  parameters = {
    'type': 'object',
    'properties': {
      'text':       { 'type': 'string', 'description': 'Text content to store.' },
      'doc_id':     { 'type': 'string', 'description': 'Unique ID for this entry. Auto-generated if omitted.' },
      'collection': { 'type': 'string', 'description': 'Collection name (namespace). Defaults to "default".' },
      'metadata':   { 'type': 'string', 'description': 'Optional JSON object of metadata to attach.' },
    },
    'required': ['text'],
  }

  def call(self, params: str | dict, **kwargs) -> dict:
    if isinstance(params, str):
      params = json.loads(params)

    text       = params['text']
    doc_id     = params.get('doc_id') or _auto_id(text)
    coll_name  = params.get('collection', 'default')
    raw_meta   = params.get('metadata', '{}')

    try:
      meta = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
    except json.JSONDecodeError:
      meta = {}

    try:
      coll = _collection(coll_name)
      coll.upsert(ids=[doc_id], documents=[text], metadatas=[meta])
      return tool_result({ 'id': doc_id, 'collection': coll_name })
    except Exception as exc:
      return tool_result(error=str(exc))


@register_tool('kb_search')
class KnowledgeSearch(BaseTool):
  description = (
    'Semantically search the vector database for text related to a query. '
    'Returns the most relevant stored documents and their similarity scores.'
  )
  parameters = {
    'type': 'object',
    'properties': {
      'query':      { 'type': 'string', 'description': 'Natural language search query.' },
      'collection': { 'type': 'string', 'description': 'Collection to search. Defaults to "default".' },
      'n_results':  { 'type': 'integer', 'description': 'Number of results to return. Defaults to 5.' },
    },
    'required': ['query'],
  }

  def call(self, params: str | dict, **kwargs) -> dict:
    if isinstance(params, str):
      params = json.loads(params)

    query     = params['query']
    coll_name = params.get('collection', 'default')
    n         = int(params.get('n_results', 5))

    try:
      coll  = _collection(coll_name)
      count = coll.count()
      if count == 0:
        return tool_result({ 'results': [], 'note': 'Collection is empty.' })

      results = coll.query(query_texts=[query], n_results=min(n, count))
      hits = [
        { 'id': doc_id, 'text': doc, 'score': score, 'metadata': meta }
        for doc_id, doc, score, meta in zip(
          results['ids'][0],
          results['documents'][0],
          results['distances'][0],
          results['metadatas'][0],
        )
      ]
      return tool_result({ 'results': hits })
    except Exception as exc:
      return tool_result(error=str(exc))


def _auto_id(text: str) -> str:
  import hashlib
  return hashlib.sha1(text.encode()).hexdigest()[:16]
