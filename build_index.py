from app.rag.loader import load_menu
from app.rag.vector_store import create_vector_db
from dotenv import load_dotenv

load_dotenv()

doc_menus = load_menu()

# for doc in doc_menus:
#     print('=== page_content ===')
#     print(doc.page_content)
#     print('=== metadata ===')
#     print(doc.metadata)
#     print()

create_vector_db(doc_menus)
