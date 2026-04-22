
from langchain_chroma import Chroma
from app.rag.chroma import get_embedding


def create_vector_db(documents): # 1회용 벡터 생성
    # ID 기반 add (collision 시 overwrite)

    embedding = get_embedding()
    
    ids = [str(doc.metadata["id"]) for doc in documents]
    
    db = Chroma(
        persist_directory="data/chroma_db",
        embedding_function=embedding,
        collection_metadata={"hnsw:space": "cosine"},
    )
    
    db.reset_collection()
    db.add_documents(documents=documents, ids=ids)
    
    
    