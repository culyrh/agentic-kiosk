# from dotenv import load_dotenv
# import os
# from langchain_openai import ChatOpenAI
# from langchain_core.prompts import ChatPromptTemplate
# from langchain_core.output_parsers import StrOutputParser

# load_dotenv()
# api_key = os.getenv("OPENAI_API_KEY")

# llm = ChatOpenAI(model="gpt-4o")

# prompt = ChatPromptTemplate.from_template("주제 {topic}에 대해 어떻게 만들어야 되는지 간략하게 설명해줘")

# parser = StrOutputParser()

# chain = prompt | llm | parser

# response = chain.invoke({"topic": "음성인식 키오스크 ReAct Agent"})
# print(response)

from app.rag.loader import load_menu
from app.rag.vector_store import create_vector_db
from app.rag.chroma import get_chroma_db
from dotenv import load_dotenv
import os

from app.tools.search_menu import search_menu 


load_dotenv()
# print(os.getenv("OPENAI_API_KEY"))

doc_menus = load_menu()
# print(doc_menus)

create_vector_db(doc_menus)
# da = data.get(include=["embeddings", "documents", "metadatas"])

# db = get_chroma_db()

#### 디버깅용 ####
# result = db.similarity_search("짭조름하고 달달한 간식 추천해줘", k = 1) 
# print(result)
# a = db.get(include=["embeddings", "documents", "metadatas"])
# print(a["documents"])


result = search_menu.invoke({
    "query": "간단히 먹을 수 있는 사이드 추천해줘",
    "category": "사이드"
    })
print(result)
