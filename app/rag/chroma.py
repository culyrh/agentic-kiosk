
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma


_embedding = None # 전역 변수
def get_embedding():
    
    global _embedding
    
    if _embedding is None: # 처음 호출 -> 모델 로딩
        _embedding = HuggingFaceEmbeddings(model_name="jhgan/ko-sroberta-multitask")
    
    return _embedding # 두번째 호출 -> 기존 반환


def get_chroma_db():

    db = Chroma(
        persist_directory="data/chroma_db",
        embedding_function=get_embedding(),
        collection_metadata={"hnsw:space": "cosine"}  # 코사인 거리 - 텍스트 검색 적합.
    )

    return db
