# 🍔 Sadollar Kiosk - AI 음성 주문 키오스크

롯데리아 매장에서 사용자가 음성으로 메뉴를 탐색하고 결제까지 완료할 수 있는 배리어 프리(Barrier-free) 음성 주문 시스템입니다.

---

## 시스템 동작 구조

```
사용자 음성
↓
STT (Whisper)
↓
텍스트
↓
AI 에이전트 (LangChain)
↓                         ↓
ChromaDB 검색              SQLite 조회 (백엔드)
(의미 기반 검색)            (정확한 데이터)
↓                         ↓
menu_id 반환    →→→        가격, 알레르기, 세트 여부
                           장바구니, 주문, 결제 처리
↓
LLM 응답 생성
↓
TTS
↓
음성 출력
```

---

## DB 구조

### SQLite 테이블 (ria_menu.db)

| 테이블 | 역할 | 데이터 수 |
|--------|------|-----------|
| menu | 단품 메뉴 전체 | 78개 |
| options | 세트 구성 선택지 (드링크/사이드/토핑) | 39개 |
| set_menus | 버거별 세트 구성 및 가격 | 23개 |
| set_options | 세트-옵션 연결 (토핑 제외) | 897개 |
| cart | 주문 중인 장바구니 (주문 시 채워짐) | - |
| orders | 결제 완료된 주문 내역 | - |
| sessions | 현재 대화 상태 저장 | - |

### 메뉴 ID 체계 (카테고리별 100번대)

| 카테고리 | ID 범위 |
|----------|---------|
| 버거 | 101 ~ 199 |
| 디저트 | 201 ~ 299 |
| 치킨 | 301 ~ 399 |
| 음료 | 401 ~ 499 |
| 아이스샷 | 501 ~ 599 |
| 토핑 | 601 ~ 699 |

### JSON 데이터 구조

**단품 메뉴 (ria_menu.json)**
```json
{
  "id": 101,
  "category": "버거",
  "name": "통다리 크리스피치킨버거(파이어핫)",
  "badge": ["NEW"],
  "price": "6,900",
  "description": "...",
  "allergy": "달걀, 밀, 대두, ...",
  "origin": "닭고기 - 브라질산",
  "nutrition": {"총중량": "231", "열량": "594", ...},
  "img_url": "https://...",
  "spicy_level": 0
}
```

**세트 메뉴 (ria_sets.json)**
```json
{
  "name": "통다리 크리스피치킨버거세트(파이어핫)",
  "burger_menu_id": 101,
  "set_price": "8,900",
  "img_url": "https://...",
  "allergy": "달걀, 밀, 대두, ...",
  "origin": "닭고기 - 브라질산",
  "calorie": "706kcal ~ 1431kcal",
  "set_id": 23
}
```

**옵션 (ria_options.json)**
```json
{"option_id": "D01", "option_type": "드링크", "menu_id": 401, "name": "콜라", "extra_price": 0}
```

---

## API 명세

서버 실행:
```bash
uvicorn api.main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs

### 메뉴
| Method | URL | 설명 |
|--------|-----|------|
| GET | /menu | 전체 메뉴 조회 |
| GET | /menu?category=버거 | 카테고리 필터 |
| GET | /menu?q=불고기 | 키워드 검색 |
| GET | /menu/{id} | 단건 조회 |
| GET | /menu/{id}/set | 세트 조회 |

### 장바구니
| Method | URL | 설명 |
|--------|-----|------|
| GET | /cart/{session_id} | 장바구니 조회 |
| POST | /cart | 장바구니 담기 |
| PUT | /cart/{cart_id} | 수량 수정 |
| DELETE | /cart/{cart_id} | 항목 삭제 |
| DELETE | /cart/session/{session_id} | 전체 비우기 |

### 주문
| Method | URL | 설명 |
|--------|-----|------|
| POST | /order | 주문 생성 |
| POST | /order/{order_id}/payment | 결제 |
| GET | /order/{session_id} | 주문 내역 조회 |

### 세션
| Method | URL | 설명 |
|--------|-----|------|
| POST | /session/{session_id} | 세션 생성 |
| GET | /session/{session_id} | 세션 조회 |
| PUT | /session/{session_id} | 세션 업데이트 |

### RAG 검색
| Method | URL | 설명 |
|--------|-----|------|
| POST | /search | 자연어 메뉴 검색 |

#### POST /search 요청 예시
```json
{
  "query": "치즈 들어가는 햄버거 추천해줘",
  "k": 5,
  "score_threshold": 0.5
}
```

---

## 환경 세팅

### 1. Python 버전
```
Python 3.10.11 권장
```

### 2. 가상환경 생성 및 활성화
```bash
py -3.10 -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 3. 패키지 설치
```bash
pip install -r requirements.txt
```

### 4. 환경변수 설정
`.env` 파일 생성 후 OpenAI API 키 입력:
```
OPENAI_API_KEY=sk-...
```

---

## DB 초기화 (최초 1회)

```bash
# 1. 테이블 생성
python db_setup.py

# 2. JSON 데이터 → DB 삽입
python insert_data.py
```

### 세트 메뉴 크롤링 (최초 1회)

세트 메뉴 데이터가 없거나 업데이트가 필요할 때 실행합니다.

```bash
# 세트 정보 크롤링 (알레르기, 열량, 원산지)
python crawling/crawling_set.py

# 세트 이미지 크롤링 (셀레니움 필요)
python crawling/crawling_setimage.py

# 크롤링 후 DB 재삽입
python insert_data.py
```

## 프로젝트 구조

```
sadollar-kiosk/
│
├── api/
│   ├── main.py                    # FastAPI 서버 진입점
│   └── routes/
│       ├── menu.py                # 메뉴 API
│       ├── cart.py                # 장바구니 API
│       ├── order.py               # 주문/결제 API
│       ├── session.py             # 세션 API
│       └── search.py              # RAG 검색 API
│
├── app/
│   ├── rag/
│   │   ├── loader.py              # ria_menu.json → Document 변환
│   │   ├── vector_store.py        # ChromaDB 임베딩 저장
│   │   └── chroma.py              # ChromaDB 연결 및 검색
│   └── tools/
│       ├── menu_tools.py          # 메뉴 검색 도구 (RAG)
│       └── cart_tools.py          # 장바구니 도구
│
├── crawling/
│   ├── crawling.py                # 단품 메뉴 크롤링 → ria_menu.json
│   ├── crawling_set.py            # 세트 메뉴 크롤링 (이미지 제외) → ria_sets.json
│   └── crawling_setimage.py       # 세트 이미지 크롤링 → ria_sets.json 업데이트
│
├── data/
│   ├── ria_menu.json              # 단품 메뉴 데이터 (badge 배열, nutrition 딕셔너리)
│   ├── ria_options.json           # 세트 구성 옵션 (드링크/사이드/토핑)
│   ├── ria_sets.json              # 세트 메뉴 데이터 (set_price = 단품+2000원)
│   └── ria_menu.db                # SQLite DB (gitignore 제외)
│
├── db/
│   └── sqlite.py                  # DB 연결 및 쿼리 함수
│
├── voice/
│   ├── stt.py                     # Whisper STT (파일 인식)
│   ├── stt_realtime.py            # Whisper STT (실시간)
│   └── tts.py                     # TTS
│
├── tests/
│   └── results/                   # STT 결과 저장
│
├── db_setup.py                    # DB 테이블 생성 (최초 1회)
├── insert_data.py                 # JSON → DB 삽입 (최초 1회)
├── test.py                        # ChromaDB 초기화 및 RAG 테스트
├── requirements.txt
└── .env                           # API 키 설정 (gitignore 제외)
```