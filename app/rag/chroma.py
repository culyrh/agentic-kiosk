# from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma


def get_chroma_db():
    embedding = OpenAIEmbeddings()
    
    db = Chroma(
        persist_directory="data/chroma_db",
        embedding_function = embedding,
    )
    
    return db