# 2026-1 산학실전 캡스톤디자인
## 사용자 의도 파악 및 맥락기반 추천 기능을 갖춘 지능형 음성 결제 에이전트

기존 키오스크의 복잡한 계층형 UI를 거칠 필요 없이 사용자의 자연스러운 음성 발화를 AI 에이전트가 스스로 분석, 판단하여 필요한 동작을 자율적으로 수행하는 무인 단말기용 음성 주문 시스템입니다.

프론트 깃허브 링크 : [Front-End](https://github.com/seb0070/sadollar-kiosk-fe)

<div align="center">

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/ramimi12"><img src="https://avatars.githubusercontent.com/ramimi12" width="100px" /></a><br/>
      <sub><b>김보람</b></sub><br/>
      <sub>백엔드 API</sub>
    </td>
    <td align="center">
      <a href="https://github.com/culyrh"><img src="https://avatars.githubusercontent.com/culyrh" width="100px" /></a><br/>
      <sub><b>박소현</b></sub><br/>
      <sub>음성 처리 · AI 에이전트</sub>
    </td>
    <td align="center">
      <a href="https://github.com/yuannnna"><img src="https://avatars.githubusercontent.com/yuannnna" width="100px" /></a><br/>
      <sub><b>유한나</b></sub><br/>
      <sub>AI 에이전트</sub>
    </td>
    <td align="center">
      <a href="https://github.com/seb0070"><img src="https://avatars.githubusercontent.com/seb0070" width="100px" /></a><br/>
      <sub><b>정세빈</b></sub><br/>
      <sub>프론트엔드</sub>
    </td>
  </tr>
</table>

</div>

---

## 목적

### 디지털 취약계층의 키오스크 이용 격차를 해소하기 위해, 음성 발화만으로 메뉴 검색부터 결제까지 전 과정을 처리하는 AI 음성 주문 키오스크를 구축한다.

---

## 시스템 아키텍처

```
사용자 음성
↓  WebSocket
Silero VAD → Whisper STT
↓
LangChain ReAct 에이전트 (GPT-4o)
↓
┌─────────────────────────────────────────┐
│  메뉴 검색        영양/가격 조회   장바구니/주문  │
│  ChromaDB         SQLite          SQLite  │
└─────────────────────────────────────────┘
↓
edge-tts → 음성 + 화면 액션 응답
```

### 설계 원칙

- **ChromaDB**: `search_menu`에서 자연어 query가 있을 때만 사용. 카테고리·뱃지·재료 제외 조건만 있는 경우 SQLite 직접 쿼리로 처리
- **장바구니/주문**: ChromaDB를 거치지 않고 SQLite 이름 매칭으로 직접 처리
- **멀티턴 대화**: 세션별 `defaultdict` + 슬라이딩 윈도우(최근 5턴) 인메모리 관리

---

## 1. 환경 세팅

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
`.env` 파일 생성 후 API 키 입력:
```
OPENAI_API_KEY=sk-...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_...
LANGCHAIN_PROJECT=sadollar-ai
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
```bash
# 세트 정보 크롤링 (알레르기, 열량, 원산지)
python crawling/crawling_set.py

# 세트 이미지 크롤링 (셀레니움 필요)
python crawling/crawling_setimage.py

# 크롤링 후 DB 재삽입
python insert_data.py
```

---

## 2. AI 에이전트 Tool 함수 목록

LangChain ReAct 에이전트가 사용하는 tool 함수 목록입니다.

| 함수 | 파일 | 기능 |
|------|------|------|
| `search_menu` | menu_tools.py | RAG 기반 메뉴 검색 (벡터+SQL 하이브리드) |
| `get_menu_by_price` | menu_tools.py | 가격 기준 메뉴 조회 (최저/최고/예산 범위) |
| `get_menu_by_nutrition` | menu_tools.py | 영양소(칼로리/당류/단백질) 기준 정렬 조회 |
| `get_menu_info` | menu_tools.py | 특정 메뉴 가격·설명 조회 |
| `get_set_info` | menu_tools.py | 세트 메뉴 정보 + 옵션 목록 |
| `add_to_cart` | cart_tools.py | 장바구니에 메뉴 추가 |
| `update_cart_quantity` | cart_tools.py | 장바구니 수량 변경 (0 이하면 자동 제거) |
| `remove_from_cart` | cart_tools.py | 장바구니에서 특정 메뉴 제거 |
| `upgrade_to_set` | cart_tools.py | 단품 버거 → 세트 전환 (음료/사이드 지정) |
| `downgrade_to_single` | cart_tools.py | 세트 → 단품 전환 |
| `view_cart` | cart_tools.py | 장바구니 목록 및 총 금액 확인 |
| `confirm_order` | cart_tools.py | 주문 완료 및 결제 처리 |
| `clear_cart` | cart_tools.py | 장바구니 전체 비우기 |

---

## 3. DB 구조

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

---

## 4. API 명세

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

---

## 5. 입력 필터링

### 1차 — 백엔드 미들웨어
- 모든 POST 요청의 text/query/message 필드 검사
- 욕설 감지 시 LLM 호출 없이 즉시 400 반환

### 2차 — WebSocket 수신 단계
- STT 결과를 에이전트 전달 전 체크
- 욕설 감지 시 에이전트 호출 없이 음성 응답만 반환

### 3차 — AI 시스템 프롬프트
- 주문 외 발화("날씨 어때", "심심해" 등)
- LLM이 의미 판단 → "주문만 도와드릴 수 있어요" 응답

---

## 6. 전체 파이프라인 테스트

프론트엔드 없이 파이프라인(STT → 에이전트 → TTS)이 정상 동작하는지 확인하는 테스트 스크립트입니다.

```bash
# 서버 실행
uvicorn api.main:app --reload

# 파이프라인 테스트 (별도 터미널)
python test_pipeline.py

# TTS 음성까지 로컬 스피커로 재생
python test_pipeline.py --play-audio
```

출력 예시:
```
[STT]  불고기버그 하나 담아줘
[정제] 불고기버거 하나 담아줘
[음성] 불고기버거를 장바구니에 담았습니다. 다른 메뉴도 추가하시겠어요?
```

---

## 7. 프로젝트 구조

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
│       ├── search.py              # RAG 검색 API
│       └── stt.py                 # STT/TTS WebSocket
│
├── app/
│   ├── agent.py                   # LangChain ReAct 에이전트
│   ├── session_context.py         # 세션 ID 관리
│   ├── latency_tracker.py         # 레이턴시 측정
│   ├── rag/
│   │   ├── loader.py              # SQLite → Document 변환
│   │   ├── vector_store.py        # ChromaDB 임베딩 저장
│   │   ├── chroma.py              # ChromaDB 연결
│   │   └── search.py              # RAG 검색 로직
│   └── tools/
│       ├── menu_tools.py          # 메뉴 검색 도구
│       └── cart_tools.py          # 장바구니/주문 도구
│
├── voice/
│   ├── stt.py                     # Whisper STT
│   ├── stt_realtime.py            # 실시간 STT
│   ├── tts.py                     # edge-tts TTS
│   └── vad_silero.py              # Silero VAD
│
├── crawling/
│   ├── crawling.py                # 단품 메뉴 크롤링
│   ├── crawling_set.py            # 세트 메뉴 크롤링
│   └── crawling_setimage.py       # 세트 이미지 크롤링
│
├── data/
│   ├── ria_menu.json              # 단품 메뉴 데이터
│   ├── ria_options.json           # 옵션 데이터
│   ├── ria_sets.json              # 세트 메뉴 데이터
│   └── ria_menu.db                # SQLite DB
│
├── db_setup.py                    # DB 테이블 생성
├── insert_data.py                 # JSON → DB 삽입
├── build_index.py                 # ChromaDB 초기화
├── test_pipeline.py               # 전체 파이프라인 테스트
├── visualize_embeddings.py        # 임베딩 벡터 시각화
├── requirements.txt
└── .env
```
