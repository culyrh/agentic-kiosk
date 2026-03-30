from dotenv import load_dotenv
load_dotenv()

from langchain.tools import tool
from app.rag.chroma import get_chroma_db


def search_menu_logic(query: str, category: str = None, badge: str = None, keyword: str = None, exclude: list = []):

    # 메타데이터 필터 구성
    conditions = []
    if category:
        conditions.append({"category": {"$eq": category}})
    if badge:
        conditions.append({"badge": {"$eq": badge}})


    if len(conditions) > 1:
        filters = {"$and": conditions}
    elif len(conditions) == 1:
        filters = conditions[0]
    else:
        filters = None


    # 벡터 검색
    db = get_chroma_db()
    results = db.similarity_search_with_score(
        query,
        k=5,
        filter=filters,
        where_document={"$contains": keyword} if keyword else None
    )

    # 제외 재료 필터링
    def is_excluded(doc):
        allergy = doc.metadata.get("allergy", "")
        return any(item in allergy for item in exclude)

    merged = [
        (doc, score) for doc, score in results
        if score < 0.5 and not is_excluded(doc)
    ]

    # ChromaDB에 없는 추가 데이터(재고) 생기면 DB조회 추가 할수도.
    return [(doc.page_content, round(score, 4)) for doc, score in merged[:3]]


@tool
def search_menu(query: str, category: str = None, badge: str = None, keyword: str = None, exclude: list = []):
    """사용자 요청에 맞는 메뉴 검색.
    category: 버거/디저트/음료/사이드.
    badge: NEW=신메뉴, BEST=베스트.
    keyword: 반드시 포함되어야 할 재료나 맛 (예: 치즈, 바질, 초코).
    exclude: 제외할 재료 목록 (예: ["쇠고기", "우유"]).
    """
    return search_menu_logic(query, category, badge, keyword, exclude)
