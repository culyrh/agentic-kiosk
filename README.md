# Sadollar Kiosk - AI 음성 주문 키오스크

기존 키오스크의 복잡한 계층형 UI를 거칠 필요 없이 사용자의 자연스러운 음성 발화를 AI 에이전트가 스스로 분석, 판단하여 필요한 동작을 자율적으로 수행하는 무인 단말기용 음성 주문 시스템입니다.

---

## 환경 세팅

```
Python 3.10.11 권장
```

### 가상환경 생성 및 활성화
```bash
py -3.10 -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 패키지 설치
```bash
pip install -r requirements.txt
```

### 환경변수 설정
`.env` 파일 생성 후 OpenAI API 키 입력:
```
OPENAI_API_KEY=sk-...
```

### DB 및 ChromaDB 초기화 (최초 1회)
```bash
# 1. 테이블 생성
python db_setup.py

# 2. JSON 데이터 → DB 삽입
python insert_data.py

# 3. ChromaDB 벡터 생성 (메뉴 검색용 임베딩)
python build_index.py
```

### 세트 메뉴 크롤링 (데이터 업데이트 시)

세트 메뉴 데이터가 변경되거나 업데이트가 필요할 때만 실행합니다.

```bash
# 세트 정보 크롤링 (알레르기, 열량, 원산지)
python crawling/crawling_set.py

# 세트 이미지 크롤링 (셀레니움 필요)
python crawling/crawling_setimage.py

# 크롤링 후 DB 재삽입
python insert_data.py
```

---

## 시스템 동작 구조

```
사용자 음성
↓
STT (Whisper)
↓
텍스트
↓
LLM 정제 (GPT-4o-mini) — STT 오인식 교정, 잡음성 발화 정리
↓
AI 에이전트 (LangChain + GPT-4o)
↓
도구 선택
↓
─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  [메뉴 검색]                    [메뉴 조회]          [장바구니/주문]           │
│  search_menu                   get_menu_info        add_to_cart             │
│       ↓                        get_menu_by_price    update_cart_quantity    │
│  어떤 경로?                     get_set_info         remove_from_cart        │
│                                      ↓              upgrade_to_set          │
│  ① exclude만 있음                  SQLite            view_cart               │
│     → SQL 전체조회                (이름/가격          confirm_order           │
│       알레르기 필터                  LIKE 검색)       clear_cart              │
│                                      ↓                    ↓                 │
│  ② badge만 있음                  정보 반환          SQLite 3단계 이름 매칭     │
│     → SQL badge LIKE 검색                          1차: 완전일치              │
│                                                    2차: AND검색              │
│  ③ category만 있음                                     + 가장 긴 토큰 병합    │
│     → SQL 카테고리 조회                             3차: 접두어 수집           │
│       (LIMIT 3, OFFSET)                                 ↓                   │
│                                                    cart/orders/order_items  │
│  ④ 그 외 (query 있음 등)                            테이블 처리               │
│     → ChromaDB 벡터 검색                                ↓                    │
│       (유사도 0.7 임계값)                           결과 반환                 │
│          ↓                                                                  │
│      텍스트 반환                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
↓
LLM 응답 생성
↓
TTS
↓
음성 출력
```

### 1. 설계 원칙

- **ChromaDB**: `search_menu`에서 query 파라미터가 있을 때만 사용
  (exclude만/카테고리만/badge만 있는 경우는 모두 SQLite로 처리)
- **카테고리 전체 조회**: SQLite LIMIT/OFFSET 페이지네이션으로 처리 (ChromaDB k 제한 우회)
- **장바구니 추가/제거**: ChromaDB를 거치지 않고 SQLite 이름 매칭으로 직접 처리
- **장바구니/주문**: SQLite `cart`, `orders` 테이블에서 전담 처리

### 2. Self-querying 미적용 이유 및 향후 계획

현재 `search_menu`는 LangChain Self-querying Retriever 대신 **수동 파라미터 추출** 방식을 사용한다.

**현재 방식 (수동 파라미터 추출)**
- LLM이 사용자 발화에서 `query`, `category`, `badge`, `exclude`, `exclude_names`, `offset` 파라미터를 직접 추출해 tool에 넘김
- tool docstring의 예시가 LLM의 파라미터 추출을 가이드
- 결과적으로 Self-querying과 동일한 효과

**Self-querying을 도입하지 않은 이유**
- DB 스키마가 아직 확정되지 않아 ChromaDB 메타데이터 구조가 바뀔 수 있음
- 현재 수동 방식으로도 `category`, `badge` 필터가 충분히 동작함

**Self-querying 도입을 고려할 시점**
- DB/ChromaDB 스키마 확정 이후
- "세트 포함 + 8000원 이하 + 매운 버거" 같은 복합 필터 쿼리 실패 케이스가 쌓일 때

### 3. 현재 한계 및 향후 개선 계획

**remove_from_cart 중복 호출**
- 현재: SYSTEM_PROMPT 지시 + 턴당 1회 플래그(`_remove_called`)로 방지
- 한계: LLM이 히스토리에서 정확한 메뉴명을 알고 있을 때 엣지케이스 발생 가능

---

## 전체 파이프라인 테스트

프론트엔드 없이 서버의 파이프라인(STT → LLM 정제 → 에이전트 → TTS 출력)이 정상 동작하는지 로컬에서 확인하는 테스트 스크립트입니다. **실제 키오스크에서는 브라우저/앱이 이 역할을 대신합니다.**

서버를 먼저 실행한 뒤, 별도 터미널에서 실행합니다.

```bash
# 서버 실행
uvicorn api.main:app --reload

# 파이프라인 테스트 - 텍스트 출력만 (별도 터미널)
python test_pipeline.py

# TTS 음성까지 로컬 스피커로 재생 (백엔드 테스트용)
python test_pipeline.py --play-audio
```

말하면 아래와 같이 출력됩니다.

```
마이크 대기 중... (Ctrl+C로 종료)

[STT]  불고기버그 하나 담아줘
[정제] 불고기버거 하나 담아줘
[음성] 불고기버거를 장바구니에 담았습니다. 다른 메뉴도 추가하시겠어요?

[STT]  음료 선택할게요
[정제] 음료 선택할게요
[음성] 음료를 선택해주세요.
[화면] 콜라
사이다
제로슈거콜라
```

`--play-audio` 옵션을 사용하면 `pygame`이 설치되어 있어야 하며, TTS 응답이 로컬 스피커로 재생됩니다.

`Ctrl+C`로 종료합니다.

---

## 1. AI 에이전트 Tool 함수 목록

LangChain ReAct 에이전트가 사용하는 tool 함수 목록입니다.

| 함수 | 파일 | 기능 |
|------|------|------|
| `search_menu` | menu_tools.py | RAG 기반 메뉴 검색 |
| `get_menu_by_price` | menu_tools.py | 가격 기준 메뉴 조회 (최저/최고/예산 범위) |
| `get_menu_by_nutrition` | menu_tools.py | 영양소(칼로리/당류/단백질) 기준 정렬 조회 |
| `get_menu_info` | menu_tools.py | 특정 메뉴 가격·설명 조회 |
| `get_set_info` | menu_tools.py | 세트 메뉴 정보 + 옵션 목록 |
| `add_to_cart` | cart_tools.py | 장바구니에 메뉴 추가 |
| `update_cart_quantity` | cart_tools.py | 장바구니 수량 변경 (0 이하면 자동 제거) |
| `remove_from_cart` | cart_tools.py | 장바구니에서 특정 메뉴 제거 |
| `upgrade_to_set` | cart_tools.py | 단품 버거 → 세트 전환 (음료/사이드 지정, 추가금액 반영) |
| `view_cart` | cart_tools.py | 장바구니 목록 및 총 금액 확인 |
| `confirm_order` | cart_tools.py | 주문 완료 및 결제 처리 |
| `clear_cart` | cart_tools.py | 장바구니 전체 비우기 |
---


## 2. DB 구조

### SQLite 테이블 (ria_menu.db)

| 테이블 | 역할 | 데이터 수 |
|--------|------|-----------|
| menu | 단품 메뉴 전체 | 78개 |
| options | 세트 구성 선택지 (드링크/사이드) | 41개 |
| set_menus | 버거별 세트 구성 및 가격 | 23개 |
| cart | 주문 중인 장바구니 | - |
| orders | 결제 완료된 주문 내역 | - |

> **set_options 테이블을 제거한 이유**
> 롯데리아의 모든 세트는 동일한 음료/사이드 옵션을 제공하므로 세트별 옵션 연결 테이블이 불필요했습니다.
> 세트 주문 시 cart 테이블의 drink_option, side_option 컬럼에 선택값을 저장하는 방식으로 단순화했습니다.

> **sessions 테이블을 제거한 이유**
> 인메모리 대화 히스토리(`defaultdict`)가 current_state, last_recommended 역할을 대신하므로 불필요했습니다.

### 테이블 상세 구조

**menu 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER | 카테고리별 100번대 고유 ID |
| category | TEXT | 버거/디저트/치킨/음료/아이스샷/토핑 |
| name | TEXT | 메뉴명 |
| badge | TEXT | 뱃지 배열 JSON (예: ["NEW", "BEST"]) |
| price | INTEGER | 단품 가격 (정수) |
| description | TEXT | 메뉴 설명 |
| img_url | TEXT | 이미지 URL |
| allergy | TEXT | 알레르기 배열 JSON (예: ["달걀", "밀"]) |
| origin | TEXT | 원산지 정보 |
| nutrition | TEXT | 영양정보 딕셔너리 JSON |
| spicy_level | INTEGER | 매운맛 단계 (0~3) |

**options 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| option_id | TEXT | D01~D20 (드링크), S01~S21 (사이드) |
| option_type | TEXT | 드링크 / 사이드 |
| menu_id | INTEGER | menu 테이블 참조 |
| extra_price | INTEGER | 기본 옵션 대비 추가 금액 |

**set_menus 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| set_id | INTEGER | 세트 고유 ID (자동 증가) |
| burger_menu_id | INTEGER | menu 테이블의 버거 ID 참조 |
| name | TEXT | 세트명 |
| set_price | INTEGER | 세트 가격 (단품 + 2,000원) |
| description | TEXT | 세트 설명 |
| img_url | TEXT | 세트 이미지 URL |
| allergy | TEXT | 알레르기 정보 |
| origin | TEXT | 원산지 정보 |
| calorie | TEXT | 열량 범위 (예: 706kcal ~ 1431kcal) |

**cart 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| cart_id | INTEGER | 장바구니 항목 ID (자동 증가) |
| session_id | TEXT | 세션 ID |
| menu_id | INTEGER | menu 테이블 참조 |
| is_set | INTEGER | 세트 여부 (0=단품, 1=세트) |
| drink_option | TEXT | 선택한 드링크 option_id |
| side_option | TEXT | 선택한 사이드 option_id |
| quantity | INTEGER | 수량 |
| unit_price | INTEGER | 단가 |

**orders 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| order_id | INTEGER | 주문 ID (자동 증가) |
| session_id | TEXT | 세션 ID |
| total_price | INTEGER | 총 결제 금액 |
| payment_method | TEXT | 결제 수단 |
| status | TEXT | pending → paid |
| created_at | TEXT | 주문 시각 |

### 메뉴 ID 체계

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
  "price": 6900,
  "allergy": ["달걀", "밀", "대두"],
  "origin": "닭고기 - 브라질산",
  "nutrition": {"총중량": "231", "열량": "594"},
  "img_url": "https://...",
  "spicy_level": 0
}
```

**세트 메뉴 (ria_sets.json)**
```json
{
  "name": "통다리 크리스피치킨버거세트(파이어핫)",
  "burger_menu_id": 101,
  "set_price": 8900,
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
python -m uvicorn api.main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs

### 메뉴
| Method | URL | 설명 |
|--------|-----|------|
| GET | /menu | 전체 메뉴 조회 |
| GET | /menu?category=버거 | 카테고리 필터 |
| GET | /menu?q=불고기 | 키워드 검색 |
| GET | /menu/{id} | 단건 조회 |
| GET | /menu/{id}/set | 버거 ID로 세트 조회 |

### 세트 메뉴
| Method | URL | 설명 |
|--------|-----|------|
| GET | /sets | 전체 세트 목록 조회 |
| GET | /sets/{set_id} | 세트 단건 조회 |

### 옵션
| Method | URL | 설명 |
|--------|-----|------|
| GET | /options | 전체 옵션 조회 |
| GET | /options?type=드링크 | 드링크 목록 |
| GET | /options?type=사이드 | 사이드 목록 |

### 장바구니
| Method | URL | 설명 |
|--------|-----|------|
| GET | /cart/{session_id} | 장바구니 조회 |
| POST | /cart | 장바구니 담기 |
| PUT | /cart/{cart_id} | 수량 직접 수정 |
| PATCH | /cart/{cart_id}/increase | 수량 +1 |
| PATCH | /cart/{cart_id}/decrease | 수량 -1 (1이면 자동 삭제) |
| DELETE | /cart/{cart_id} | 항목 삭제 |
| DELETE | /cart/session/{session_id} | 전체 비우기 |

### 주문
| Method | URL | 설명 |
|--------|-----|------|
| POST | /order | 주문 생성 |
| POST | /order/{order_id}/payment | 결제 |
| GET | /order/{session_id} | 주문 내역 조회 |

### RAG 검색
| Method | URL | 설명 |
|--------|-----|------|
| POST | /search | 자연어 메뉴 검색 |

### 헬스체크
| Method | URL | 설명 |
|--------|-----|------|
| GET | /health | 서버 상태 확인 |

---

## 입력 필터링

### 1차 필터링 (백엔드 미들웨어)

`api/main.py`에 미들웨어로 구현되어 있습니다.

- 모든 POST 요청의 text/query/message 필드 검사
- 욕설 감지 시 LLM 호출 없이 즉시 400 반환

### 2차 필터링 (WebSocket)

`api/routes/stt.py`의 `process_and_send`에서 `refined_text` 에이전트 전달 전 체크합니다.

- 욕설 감지 시 에이전트 호출 없이 음성 응답만 반환

### 3차 필터링 (AI 시스템 프롬프트)

- "날씨 어때", "심심해" 등 주문 외 발화
- LLM이 의미 판단 → "주문만 도와드릴 수 있어요" 응답

---

## 프로젝트 구조

```
sadollar-kiosk/
│
├── api/
│   ├── main.py                    # FastAPI 서버 진입점 + 욕설 필터링 미들웨어
│   └── routes/
│       ├── menu.py                # 메뉴 API
│       ├── sets.py                # 세트 메뉴 API
│       ├── options.py             # 옵션 API
│       ├── cart.py                # 장바구니 API
│       ├── order.py               # 주문/결제 API
│       ├── search.py              # RAG 검색 API (입구 역할만)
│       └── stt.py                 # STT/TTS API + WebSocket 욕설 필터링
│
├── app/
│   ├── agent.py                   # LangChain ReAct 에이전트
│   ├── refine.py                  # STT 오인식 교정
│   ├── session_context.py         # 세션 ID 관리
│   ├── rag/
│   │   ├── loader.py              # ria_menu.json → Document 변환
│   │   ├── vector_store.py        # ChromaDB 임베딩 저장
│   │   ├── chroma.py              # ChromaDB 연결 및 검색
│   │   └── search.py              # RAG 검색 로직 (AI 로직)
│   └── tools/
│       ├── menu_tools.py          # 메뉴 검색 도구
│       └── cart_tools.py          # 장바구니/주문 도구
│
├── crawling/
│   ├── crawling.py                # 단품 메뉴 크롤링 → ria_menu.json
│   ├── crawling_set.py            # 세트 메뉴 크롤링 → ria_sets.json
│   └── crawling_setimage.py       # 세트 이미지 크롤링
│
├── data/
│   ├── ria_menu.json              # 단품 메뉴 (price/badge/allergy 정수·배열)
│   ├── ria_options.json           # 세트 구성 옵션 (드링크/사이드)
│   ├── ria_sets.json              # 세트 메뉴 (set_price = 단품+2,000원)
│   └── ria_menu.db                # SQLite DB (gitignore 제외)
│
├── db/
│   └── sqlite.py                  # DB 연결 및 쿼리 함수
│
├── voice/
│   ├── stt.py                     # Whisper STT (파일 인식)
│   ├── stt_realtime.py            # Whisper STT (실시간)
│   └── tts.py                     # TTS (edge-tts)
│
├── db_setup.py                    # DB 테이블 생성 (최초 1회)
├── insert_data.py                 # JSON → DB 삽입 (최초 1회)
├── build_index.py                 # ChromaDB 초기화 (최초 1회)
├── test_pipeline.py               # 전체 파이프라인 테스트
├── requirements.txt
└── .env                           # API 키 설정 (gitignore 제외)
```
