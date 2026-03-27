# 크롤링, 메뉴 db, 메뉴 json 완성.
-> 카테고리, 상품명, 가격, 이미지 등 다 포함됨.



## 환경 설정

### 1. 가상환경 생성 및 활성화

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

## 실행

```bash
uvicorn api.main:app --reload
```

## 프로젝트 구조

```
sadollar-ai/
│
├── data/
│   ├── menu.json              # 크롤링 결과물
│   ├── menu.db                # SQLite DB 파일
│   └── chroma/                # ChromaDB 저장 디렉토리
│
├── ingestion/                 # [사전 준비] 1회성 파이프라인
│   ├── crawler.py             # 롯데리아 크롤링 (BS4/Selenium)
│   ├── sqlite_loader.py       # menu.json → SQLite
│   └── chroma_loader.py       # menu.json → 임베딩 → ChromaDB
│
├── db/
│   ├── sqlite.py
│   └── chroma.py
│
├── tools/
│   ├── search_menu.py         # ChromaDB 시맨틱 검색
│   ├── get_menu_by_name.py    # SQLite 이름 정확 조회
│   └── get_menu_detail.py     # SQLite 상세 정보 조회
│
├── agent/
│   ├── react_agent.py         # ReAct 루프 구현
│   └── prompts.py             # 시스템 프롬프트
│
├── voice/
│   ├── stt.py                 # Whisper STT
│   └── tts.py                 # TTS
│
├── api/
│   ├── main.py
│   └── routes/
│       ├── order.py           # POST /order
│       └── menu.py            # GET /menu, GET /menu/{id}
│
├── config.py
├── main.py
└── requirements.txt
```
