# 🍔 Sadollar Kiosk - AI 음성 주문 키오스크

롯데리아 매장에서 사용자가 음성으로 메뉴를 탐색하고 결제까지 완료할 수 있는 배리어 프리(Barrier-free) 음성 주문 시스템입니다.

---

## 프로젝트 구조
```
sadollar-kiosk/
│
├── data/                          # 데이터 파일 모음
│   ├── ria_menu.json              # 단품 메뉴 데이터 (82개, 카테고리별 100번대 id)
│   ├── ria_options.json           # 세트 구성 옵션 (드링크/사이드/토핑 43개)
│   ├── ria_sets_raw.json          # 세트 메뉴 데이터 (23개)
│   └── ria_menu.db                # SQLite DB 파일 (gitignore 제외)
│
├── app/
│   ├── rag/
│   │   ├── loader.py              # ria_menu.json → Document 변환
│   │   ├── vector_store.py        # ChromaDB 임베딩 저장
│   │   └── chroma.py              # ChromaDB 연결 및 검색
│   │
│   └── tools/
│       ├── menu_tools.py          # 메뉴 검색 도구 (RAG)
│       └── cart_tools.py          # 장바구니 도구
│
├── crawling/
│   ├── crawling.py                # 롯데리아 단품 메뉴 크롤링
│   ├── crawling_sets.py           # 롯데리아 세트 메뉴 크롤링
│   ├── db.py                      # 크롤링 결과 DB 저장
│   └── export_js.py               # JS 데이터 추출
│
├── voice/
│   └── stt.py                     # Whisper STT 음성 인식
│
├── tests/
│   ├── 뉴스녹음.m4a
│   └── results/                   # STT 결과 저장 디렉토리
│
├── db_setup.py                    # DB 테이블 생성 스크립트 (최초 1회)
├── insert_data.py                 # JSON → DB 데이터 삽입 스크립트 (최초 1회)
├── add_imgurl.py                  # img_url 매칭 스크립트 (최초 1회)
├── test.py                        # RAG 메뉴 검색 테스트
├── requirements.txt
└── .env                           # OpenAI API 키 설정 (gitignore 제외)
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
AI 에이전트 (LangChain + GPT-4o)
↓
도구 선택
↓
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  [메뉴 검색]              [메뉴 조회]         [장바구니/주문]     │
│  search_menu              get_menu_info      add_to_cart       │
│                           get_menu_by_price  remove_from_cart  │
│       ↓                        ↓             view_cart         │
│  query(의미) 있음?              ↓             confirm_order     │
│  ┌──YES──┐               SQLite              clear_cart        │
│  ↓       ↓               (이름 LIKE 검색)          ↓            │
│ ChromaDB  SQLite               ↓             SQLite            │
│ (벡터검색) (카테고리           메뉴 정보      (이름 기반 매칭      │ 
│  의미기반)  전체조회,           반환          → cart/orders      │ 
│     ↓      LIMIT+OFFSET)                     테이블 처리)       │ 
│  텍스트     ↓                                      ↓           │
│  반환      텍스트 반환                          결과 반환        │
└────────────────────────────────────────────────────────────────┘
↓
LLM 응답 생성
↓
TTS
↓
음성 출력
```

### 설계 원칙
- **ChromaDB**: `search_menu`에서 의미 기반 쿼리(query 파라미터)가 있을 때만 사용
- **카테고리 전체 조회**: SQLite LIMIT/OFFSET 페이지네이션으로 처리 (ChromaDB k 제한 우회)
- **장바구니 추가/제거**: ChromaDB를 거치지 않고 SQLite 이름 매칭으로 직접 처리
- **장바구니/주문**: SQLite `cart`, `orders` 테이블에서 전담 처리

### Self-querying 미적용 이유 및 향후 계획

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

### 현재 한계 및 향후 개선 계획

**대화 히스토리**
- 현재: 메모리(`defaultdict`) 기반 → 서버 재시작 시 히스토리 소멸
- 현재: 대화가 길어질수록 히스토리가 무한정 쌓여 토큰 비용 증가
- 향후: Redis/DB 영속화, 슬라이딩 윈도우(최근 N턴만 유지) 도입 예정

**remove_from_cart 중복 호출**
- 현재: SYSTEM_PROMPT 지시 + 턴당 1회 플래그(`_remove_called`)로 방지
- 한계: LLM이 히스토리에서 정확한 메뉴명을 알고 있을 때 엣지케이스 발생 가능

**주문 외 발화 처리**
- 현재: 별도 필터 없음 → LLM이 주문 외 질문도 응답해 비용 낭비
- 향후: 백엔드 미들웨어(1차) + SYSTEM_PROMPT(2차) 2단계 필터링 예정 (Issue 참고)

---

## DB 구조

### SQLite 테이블 (ria_menu.db)

| 테이블 | 역할 | 데이터 수 |
|--------|------|-----------|
| menu | 단품 메뉴 전체 | 82개 |
| options | 세트 구성 선택지 (드링크/사이드/토핑) | 43개 |
| set_menus | 버거별 세트 구성 및 가격 | 23개 |
| set_options | 세트-옵션 연결 | 989개 |
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

# 2. img_url 매칭
python add_imgurl.py

# 3. JSON 데이터 → DB 삽입
python insert_data.py
```

---

## RAG 메뉴 검색 테스트

`ria_menu.json` → ChromaDB 임베딩 저장 → 유사도 검색까지 테스트합니다.
```bash
python test.py
```

처음 실행 시 ChromaDB가 생성됩니다. 이후 실행부터는 기존 DB에 upsert됩니다.

> ⚠️ 현재 test.py는 매번 실행 시 모델을 새로 로드하므로 속도가 느립니다.
> FastAPI 서버에 붙이면 모델이 메모리에 유지되어 속도가 개선됩니다.

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

### 녹음파일 인식

```bash
# 기본 (medium 모델)
python voice/stt.py tests/뉴스녹음.m4a

# 모델 크기 지정
python voice/stt.py tests/뉴스녹음.m4a small
python voice/stt.py tests/뉴스녹음.m4a large-v3
python voice/stt.py tests/뉴스녹음.m4a large-v3-turbo
```

결과는 터미널에 출력되고 `tests/results/`에 텍스트 파일로 저장됩니다.
```
tests/results/뉴스녹음_medium_20260326_210639.txt
```

### 실시간 음성 인식

마이크로 말하면 발화가 끝나는 시점을 자동으로 감지해 바로 인식합니다.

```bash
# 기본 (small 모델, 한국어)
python voice/stt_realtime.py

# 옵션 지정
python voice/stt_realtime.py --model small --device cpu --language ko

# 주변 소음이 많을 때 (임계값을 높여 잡음 오인식 방지)
python voice/stt_realtime.py --threshold 0.03
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--model` | `small` | 모델 크기 (tiny / small / medium / large-v3) |
| `--device` | `cpu` | 추론 장치 (cpu / cuda) |
| `--language` | `ko` | 인식 언어 코드 |
| `--threshold` | `0.01` | 음성 감지 민감도 — 낮을수록 민감, 높을수록 잡음 무시 |

실행하면 마이크 대기 상태가 되고, 말을 마치면 약 0.8초 무음 후 자동으로 인식해 출력합니다.

```
[실시간 STT] 마이크 대기 중... (Ctrl+C로 종료)

[인식] 안녕하세요, 주문하고 싶어요.
      (1.23초)
```

`Ctrl+C` 로 종료합니다.

---

## AI 에이전트 Tool 함수 목록

LangChain ReAct 에이전트가 사용하는 tool 함수 목록입니다.

| 함수 | 파일 | 기능 |
|------|------|------|
| `search_menu` | menu_tools.py | RAG 기반 메뉴 검색 |
| `get_menu_by_price` | menu_tools.py | 가격 기준 메뉴 조회 (최저/최고/예산 범위) |
| `get_menu_info` | menu_tools.py | 특정 메뉴 가격·설명 조회 |
| `add_to_cart` | cart_tools.py | 장바구니에 메뉴 추가 |
| `remove_from_cart` | cart_tools.py | 장바구니에서 특정 메뉴 제거 |
| `view_cart` | cart_tools.py | 장바구니 목록 및 총 금액 확인 |
| `confirm_order` | cart_tools.py | 주문 완료 및 결제 처리 |
| `clear_cart` | cart_tools.py | 장바구니 전체 비우기 |
