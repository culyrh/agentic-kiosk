### 크롤링, 단품 메뉴 db, 메뉴 json 완성.

-> 카테고리, 상품명, 가격, 이미지 등 다 포함됨. ( 총 78 개 메뉴 )


⚠️ 세트 메뉴 크롤링 필요함.

ria_menu.json          ← 현재처럼 단품 메뉴 (버거, 디저트, 드링크 각각)

ria_options.json       ← 세트 구성 옵션 (세트_디저트 선택지, 세트_드링크 선택지, 토핑)

ria_sets.json          ← 세트메뉴 (어떤 버거 + 어떤 옵션 선택 가능한지)


---

### 현재 실행 구조

test.py 실행 → Python 프로세스 시작 → 메모리 초기화 → _embedding = None
                                                              ↓
                                                         모델 로드 (느림)
                                                         
test.py 종료 → 프로세스 종료 → 메모리 해제 → _embedding 사라짐


test.py 재실행 → 또 새 프로세스 → _embedding = None → 또 모델 로드 (느림)


=> 현재 테스트 목적으로 매번 test.py를 실행 하므로 속도 느림, FastAPI 서버에 붙이면 속도 개선.

---

롯데리아 메뉴 데이터를 기반으로
**메뉴 조회 API + AI 연동용 데이터 시스템**을 구축한 백엔드 프로젝트입니다.

---

## 📌 프로젝트 개요

본 프로젝트는 음성 기반 주문 시스템을 위한 백엔드로,
메뉴 데이터를 수집하고 AI 및 프론트엔드가 사용할 수 있도록 API 형태로 제공합니다.

### 전체 흐름

```text
크롤링 → JSON → SQLite DB → 조회 함수 → FastAPI → AI/프론트
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

### 녹음파일 인식

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

<br>

## 프로젝트 구조

파일: `db/sqlite.py`

지원 기능:

* 메뉴 목록 조회
* 메뉴 ID 조회
* 메뉴 이름 조회
* 키워드 검색

---

### 4. FastAPI API 서버

#### 📍 엔드포인트

| Method | URL           | 설명       |
| ------ | ------------- | -------- |
| GET    | `/menu`       | 메뉴 목록 조회 |
| GET    | `/menu?q=불고기` | 키워드 검색   |
| GET    | `/menu/{id}`  | 메뉴 상세 조회 |

---

### 5. AI 연동용 Tool

AI 파트에서 DB를 직접 다루지 않고
**함수 형태로 사용할 수 있도록 제공**

#### 사용 예시

```python
from tools.get_menu_by_name import run

run("한우불고기 세트")
```

---

## 📁 프로젝트 구조

```text
sadollar-ai/
│
├── data/
│   ├── menu.json
│   └── menu.db
│
├── ingestion/
│   ├── crawler.py
│   └── sqlite_loader.py
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
│   ├── stt.py                 # Whisper STT (파일 인식)
│   ├── stt_realtime.py        # Whisper STT (실시간 마이크 인식)
│   └── tts.py                 # TTS
│
├── api/
│   ├── __init__.py
│   ├── main.py
│   └── routes/
│       ├── __init__.py
│       └── menu.py
│
├── config.py
├── main.py
└── requirements.txt
```
