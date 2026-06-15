  # [2026-1 산학실전 캡스톤디자인] - 사용자 의도 파악 및 맥락기반 추천 기능을 갖춘 지능형 음성 결제 에이전트

기존 키오스크의 복잡한 계층형 UI를 거칠 필요 없이 사용자의 자연스러운 음성 발화를 AI 에이전트가 스스로 분석, 판단하여 필요한 동작을 자율적으로 수행하는 무인 단말기용 음성 주문 시스템입니다. ([Front-End](https://github.com/seb0070/sadollar-kiosk-fe))

<div align="center">

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/ramimi12"><img src="https://avatars.githubusercontent.com/ramimi12" width="80px" /></a><br/>
      <sub><b>김보람</b></sub><br/>
    </td>
    <td align="center">
      <a href="https://github.com/culyrh"><img src="https://avatars.githubusercontent.com/culyrh" width="80px" /></a><br/>
      <sub><b>박소현</b></sub><br/>
    </td>
    <td align="center">
      <a href="https://github.com/yuannnna"><img src="https://avatars.githubusercontent.com/yuannnna" width="80px" /></a><br/>
      <sub><b>유한나</b></sub><br/>
    </td>
    <td align="center">
      <a href="https://github.com/seb0070"><img src="https://avatars.githubusercontent.com/seb0070" width="80px" /></a><br/>
      <sub><b>정세빈</b></sub><br/>
    </td>
  </tr>
</table>

</div>

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| **AI / LLM** | GPT-4o, LangChain ReAct, ChromaDB, ko-sroberta-multitask |
| **음성 처리** | Whisper API, Silero VAD, edge-tts |
| **백엔드** | FastAPI, SQLite, WebSocket |
| **프론트엔드** | React |
| **인프라** | AWS EC2, Docker |

---

## 목적

### 디지털 취약계층의 키오스크 이용 격차 해소를 위해, 음성 발화만으로 메뉴 검색부터 결제까지 전 과정을 처리하는 AI 음성 주문 키오스크를 구축한다.

---

## 시스템 아키텍처

```
사용자 음성
↓  WebSocket
Silero VAD → Whisper STT
↓
LangChain ReAct 에이전트 (GPT-4o)
↓
┌────────────────────────────────────────────────┐
│  메뉴 검색     영양/가격 조회   장바구니/주문  │
│  ChromaDB         SQLite            SQLite     │
└────────────────────────────────────────────────┘
↓
edge-tts → 음성 + 화면 액션 응답
```

---

## 구현 내용

### I. 데이터 구축

롯데리아 공식 사이트를 Selenium 기반 크롤러로 수집하여 단품 78개, 세트 23개, 옵션 41개를 SQLite DB에 구축하였다. 메뉴명·설명·원산지를 하나의 텍스트로 결합하여 ChromaDB에 벡터로 저장하고, 가격·카테고리·알레르기·뱃지·매운맛 단계는 metadata로 분리하여 벡터 검색과 조건 필터링을 독립적으로 처리할 수 있도록 설계하였다.

### II. 음성 처리 (STT / VAD / TTS)

STT는 4개 모델(whisper-ko-zeroth, Qwen, Whisper small 로컬, Whisper API)을 화자 4인·환경 2종·총 320개 샘플로 비교 평가하여 Whisper API(평균 CER 7.76%, 응답속도 1,394ms)를 최종 채택하였다. 발화 구간 검출에는 Silero VAD를 적용하여 512 sample(32ms) 단위로 배경 소음과 실제 발화를 구분하며, 발화 시작 전 128ms pre-roll을 포함하여 앞 음절 누락을 방지하였다. TTS는 Microsoft edge-tts(ko-KR-SunHiNeural)를 채택하였으며, LLM 응답 전체를 기다리지 않고 문장 단위로 즉시 합성·전송하는 스트리밍 방식으로 체감 응답속도를 단축하였다.

### III. AI 에이전트 (LangChain ReAct + RAG)

에이전트는 LangChain ReAct 워크플로우로 구현하였으며 GPT-4o(temperature=0)를 사용한다. 메뉴 검색은 자연어 query가 있을 때 ChromaDB 벡터 검색을, 카테고리·뱃지 등 조건 필터가 명확한 경우 SQLite 직접 쿼리로 자동 분기하는 하이브리드 방식을 적용하였다. STT 오인식에 대응하여 메뉴 조회 시 ① 완전 일치 → ② 토큰 AND LIKE → ③ 접두어 단계별 수집의 3단계 퍼지 매칭을 구현하였다. 멀티턴 대화는 세션별 슬라이딩 윈도우(최근 5턴)로 관리하며, TYPE_SELECT → DRINK_SELECT → SIDE_SELECT로 이어지는 주문 흐름에서 이전 선택값을 히스토리에서 참조하여 연속적인 맥락을 유지한다.

### IV. 백엔드 / 프론트엔드

백엔드는 초기 Spring + FastAPI 이중 구조에서 FastAPI 단일 서버로 통합하였다. 욕설 필터링은 ① 백엔드 미들웨어 → ② WebSocket 수신 → ③ 시스템 프롬프트의 3단계로 구현하였으며, 3분 비활성 시 장바구니·히스토리 자동 초기화 및 TIMEOUT 액션 전송 기능을 추가하였다. 프론트엔드는 React로 개발하였으며 KioskScaler 컴포넌트로 430px 기준 화면 비율을 자동 조정하여 실제 키오스크 환경에서도 동일한 UI를 제공한다.

---

## 주요 기능

- **음성 주문**: 자연어 발화로 메뉴 검색, 장바구니 담기, 수량 변경, 취소, 결제까지 전 과정 처리
- **의미 기반 메뉴 검색**: "가볍게 먹을 수 있는 거", "새우 빼고 덜 매운 거" 등 키워드 없이도 의도에 맞는 메뉴 검색
- **맥락 기반 대화**: 세션별 슬라이딩 윈도우(최근 5턴)로 대화 흐름 유지, 이전 발화 참조 가능
- **STT 오인식 교정**: "불고기버그" → "불고기버거" 등 음성 인식 오류를 에이전트가 자동 교정
- **욕설 필터링**: 백엔드 미들웨어 → WebSocket → 시스템 프롬프트 3단계 필터링

---

## 실행 방법

### 요구사항
```
Python 3.10.11
```

### 설치
```bash
# 가상환경 생성 및 활성화
py -3.10 -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # Mac/Linux

# 패키지 설치
pip install -r requirements.txt
```

### 환경변수 설정
`.env` 파일 생성:
```
OPENAI_API_KEY=sk-...
```

### DB 및 벡터 DB 초기화 (최초 1회)
```bash
python db_setup.py      # 테이블 생성
python insert_data.py   # 데이터 삽입
python build_index.py   # ChromaDB 벡터 생성
```

### 서버 실행
```bash
python -m uvicorn api.main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs

---

## 데이터 구조

### SQLite (ria_menu.db)

| 테이블 | 역할 | 데이터 수 |
|--------|------|-----------|
| menu | 단품 메뉴 | 78개 |
| set_menus | 버거별 세트 구성 및 가격 | 23개 |
| options | 드링크/사이드 옵션 | 41개 |
| cart | 세션별 장바구니 | - |
| orders | 결제 완료 주문 내역 | - |

### ChromaDB
- 임베딩 모델: `jhgan/ko-sroberta-multitask`
- 저장 형식: 메뉴명·설명·원산지를 `page_content`로, 가격·카테고리·알레르기·뱃지를 `metadata`로 분리 저장
- 유사도 기준: cosine distance

---

## AI 에이전트 Tool 목록

| 분류 | 함수 | 기능 |
|------|------|------|
| 메뉴 | `search_menu` | 자연어 기반 메뉴 검색 (벡터+SQL 하이브리드) |
| 메뉴 | `get_menu_info` | 특정 메뉴 가격·설명 조회 |
| 메뉴 | `get_menu_by_price` | 가격 기준 조회 |
| 메뉴 | `get_menu_by_nutrition` | 영양소(칼로리/당류/단백질) 기준 조회 |
| 메뉴 | `get_set_info` | 세트 메뉴 정보 및 옵션 조회 |
| 장바구니 | `add_to_cart` | 메뉴 추가 |
| 장바구니 | `update_cart_quantity` | 수량 변경 |
| 장바구니 | `remove_from_cart` | 항목 제거 |
| 장바구니 | `upgrade_to_set` | 단품 → 세트 전환 |
| 장바구니 | `downgrade_to_single` | 세트 → 단품 전환 |
| 장바구니 | `view_cart` / `clear_cart` | 조회 / 전체 비우기 |
| 주문 | `confirm_order` | 주문 완료 및 결제 처리 |

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
