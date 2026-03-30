
from app.rag.loader import load_menu
from app.rag.vector_store import create_vector_db_1
from app.rag.chroma import get_chroma_db
from dotenv import load_dotenv
from app.tools.menu_tools import search_menu_logic


from app.tools.menu_tools import search_menu 


load_dotenv()

doc_menus = load_menu()


create_vector_db_1(doc_menus)



# db = get_chroma_db()
# query = "치즈 두장 들어가는 햄버거 추천해줘"
# results = db.similarity_search_with_score(query, k = 10)
# filtered = [(doc, score) for doc, score in results if score < 0.5]
# for doc, score in filtered:
#     print(f"[유사도]: {score}") # 0 에 가까울수록 유사함.
#     print(doc.page_content)
#     print("-" * 50)
    
    


result = search_menu.invoke({ ## 지금은 수동으로, agent연결 후 자동 ##
    "query": "바질 들어가는 햄버거 추천해줘",
    # "exclude": ["우유"],
    # "category": "버거",
    # "keyword": "바질",
    })


for doc, score in result:
    print(f"[score: {score}]") # 0 에 가까울수록 유사함.
    print(doc)
    print("-" * 50)
 