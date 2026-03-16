import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_community.document_loaders import TextLoader

from config import (
    CHROMA_DIR, EMBED_MODEL, CHUNK_SIZE, CHUNK_OVERLAP,
    INDEX_EXTENSIONS, INDEX_IGNORE_DIRS,
)

docs = []

for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in INDEX_IGNORE_DIRS]
    for file in files:
        if file.endswith(INDEX_EXTENSIONS):
            path = os.path.join(root, file)
            loader = TextLoader(path)
            docs.extend(loader.load())

splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
)

chunks = splitter.split_documents(docs)

embeddings = OllamaEmbeddings(model=EMBED_MODEL)

db = Chroma.from_documents(
    chunks,
    embeddings,
    persist_directory=CHROMA_DIR,
)

print(f"Indexed {len(chunks)} chunks into '{CHROMA_DIR}'")
