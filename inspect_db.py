from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

from config import CHROMA_DIR, EMBED_MODEL

embeddings = OllamaEmbeddings(model=EMBED_MODEL)

db = Chroma(
    persist_directory=CHROMA_DIR,
    embedding_function=embeddings
)

data = db.get()

print(f"Total documents in DB: {len(data['documents'])}")
for i, doc in enumerate(data["documents"][:10]):
    meta = data["metadatas"][i] if data["metadatas"] else {}
    print(f"\n--- Document {i} [{meta.get('path', '?')}] ---\n")
    print(doc[:500])
