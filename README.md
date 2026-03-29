### 크롤링, 단품 메뉴 db, 메뉴 json 완성.
-> 카테고리, 상품명, 가격, 이미지 등 다 포함됨. ( 총 78 개 메뉴 )


⚠️ 세트 메뉴 크롤링 필요함.

ria_menu.json          ← 현재처럼 단품 메뉴 (버거, 디저트, 드링크 각각)

ria_options.json       ← 세트 구성 옵션 (세트_디저트 선택지, 세트_드링크 선택지, 토핑)

ria_sets.json          ← 세트메뉴 (어떤 버거 + 어떤 옵션 선택 가능한지)



---

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

---

## RAG 메뉴 검색 테스트

`menu.json` → ChromaDB 임베딩 저장 → 유사도 검색까지 테스트합니다.

### 사전 준비

`.env` 파일에 OpenAI API 키 필요:

```
OPENAI_API_KEY=sk-...
```

### 실행

```bash
python test.py
```

처음 실행 시 `data/chroma_db/`가 생성됩니다. 이후 실행부터는 기존 DB에 upsert됩니다.

---

## STT (음성 인식)

허깅페이스 허브에서 Whisper 모델을 로컬로 다운로드해 추론합니다. OpenAI API를 사용하지 않습니다.

- 모델: `Systran/faster-whisper-{size}`
- 처음 실행 시 자동 다운로드, 이후 캐시에서 로드

### 모델 크기 선택

| 모델 | 다운로드 크기 | 속도 | 한국어 정확도 |
|------|-------------|------|--------------|
| small | ~500MB | 빠름 | 보통 |
| medium | ~1.5GB | 중간 | 좋음 |
| large-v3 | ~3GB | 느림 | 매우 좋음 |
| large-v3-turbo | ~1.6GB | 중간 | 매우 좋음 |

### 실행

```bash
# 기본 (medium 모델)
python voice/stt.py tests/뉴스녹음.m4a

# 모델 크기 지정
python voice/stt.py tests/뉴스녹음.m4a small
python voice/stt.py tests/뉴스녹음.m4a large-v3
python voice/stt.py tests/뉴스녹음.m4a large-v3-turbo
```

결과는 터미널에 출력되고 `tests/results/` 에 텍스트 파일로 저장됩니다.

```
tests/results/뉴스녹음_medium_20260326_210639.txt
```

---

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
