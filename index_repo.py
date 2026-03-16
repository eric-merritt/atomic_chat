import os
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import (
    CHROMA_DIR, EMBED_MODEL, CHUNK_SIZE, CHUNK_OVERLAP,
    INDEX_EXTENSIONS, INDEX_IGNORE_DIRS,
)

# ── CONFIG ─────────────────────────────────────────────
REPO_ROOT = "."  # root of your repo

# ── STEP 1: Walk repo and load documents ───────────────
documents = []

for root, dirs, files in os.walk(REPO_ROOT):
    dirs[:] = [d for d in dirs if d not in INDEX_IGNORE_DIRS]

    for file in files:
        if file.endswith(INDEX_EXTENSIONS):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                documents.append(Document(page_content=content, metadata={"path": path}))
            except Exception as e:
                print(f"Skipping {path}: {e}")

print(f"Loaded {len(documents)} raw documents.")

# ── STEP 2: Chunk documents ───────────────────────────
splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
chunked_documents = []

for doc in documents:
    chunks = splitter.split_text(doc.page_content)
    for i, chunk in enumerate(chunks):
        chunked_documents.append(Document(
            page_content=chunk,
            metadata={**doc.metadata, "chunk": i}
        ))

print(f"Total chunks after splitting: {len(chunked_documents)}")

# ── STEP 3: Build Chroma DB ───────────────────────────
embeddings = OllamaEmbeddings(model=EMBED_MODEL)
db = Chroma.from_documents(
    chunked_documents,
    embedding=embeddings,
    persist_directory=CHROMA_DIR
)

# ── STEP 4: Persist DB ────────────────────────────────
print(f"Chroma DB successfully persisted to '{CHROMA_DIR}'")