import os
from dotenv import load_dotenv
load_dotenv()

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma


_embedding = None
_db = None

def get_embedding():
    global _embedding
    if _embedding is None:
        model_name = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
        _embedding = HuggingFaceEmbeddings(model_name=model_name)
    return _embedding


def get_chroma_db():
    global _db
    if _db is None:
        _db = Chroma(
            persist_directory="data/chroma_db",
            embedding_function=get_embedding(),
            collection_metadata={"hnsw:space": "cosine"}
        )
    return _db
