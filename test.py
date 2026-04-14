
from app.rag.loader import load_menu
from app.rag.vector_store import create_vector_db_1
from dotenv import load_dotenv



load_dotenv()

doc_menus = load_menu()


create_vector_db_1(doc_menus)

