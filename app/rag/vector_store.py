
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma


def create_vector_db(documents):  # upsert 구조 - 중복 방지
    
    embedding = OpenAIEmbeddings()
    
    ids = [str(doc.metadata["id"]) for doc in documents]
    
    db = Chroma(
        persist_directory="data/chroma_db",
        embedding_function = embedding,
    )
    db.add_documents(documents=documents, ids=ids)
    
    
    