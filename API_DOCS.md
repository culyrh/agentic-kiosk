# 📋 Sadollar Kiosk API 문서

Base URL: `http://127.0.0.1:8000`

---

## 메뉴

| 카테고리 | 메서드 | 엔드포인트 | 설명 | 입력 | 출력 | 예외처리 / 정책 |
|----------|--------|-----------|------|------|------|----------------|
| menu | GET | /menu | 전체 메뉴 조회 | - | `{"items": [{id, name, category, badge, price, img_url, spicy_level}]}` | - |
| menu | GET | /menu?category=버거 | 카테고리 필터 | query: `category` | `{"items": [...]}` | 없는 카테고리면 빈 배열 반환 |
| menu | GET | /menu?q=불고기 | 키워드 검색 | query: `q` | `{"items": [...]}` | 없는 키워드면 빈 배열 반환 |
| menu | GET | /menu/{id} | 단건 조회 | path: `menu_id` | `{id, name, category, badge, price, img_url, allergy, origin, nutrition, spicy_level}` | 없는 ID → 404 |
| menu | GET | /menu/{id}/set | 버거 ID로 세트 조회 | path: `menu_id` | `{"set": {set_id, burger_menu_id, name, set_price, img_url, allergy, origin, calorie}}` | 세트 없음 → 404 |

---

## 세트 메뉴

| 카테고리 | 메서드 | 엔드포인트 | 설명 | 입력 | 출력 | 예외처리 / 정책 |
|----------|--------|-----------|------|------|------|----------------|
| sets | GET | /sets | 전체 세트 목록 조회 | - | `{"items": [{set_id, burger_menu_id, name, set_price, img_url, allergy, origin, calorie, burger_name, burger_img_url}]}` | - |
| sets | GET | /sets/{set_id} | 세트 단건 조회 | path: `set_id` | `{set_id, burger_menu_id, name, set_price, img_url, allergy, origin, calorie, burger_name, burger_img_url}` | 없는 ID → 404 |

---

## 옵션

| 카테고리 | 메서드 | 엔드포인트 | 설명 | 입력 | 출력 | 예외처리 / 정책 |
|----------|--------|-----------|------|------|------|----------------|
| options | GET | /options | 전체 옵션 조회 | - | `{"items": [{option_id, option_type, extra_price, name, price, img_url}]}` | - |
| options | GET | /options?type=드링크 | 드링크 목록 조회 | query: `type` | `{"items": [...]}` | 없는 타입이면 빈 배열 반환 |
| options | GET | /options?type=사이드 | 사이드 목록 조회 | query: `type` | `{"items": [...]}` | 없는 타입이면 빈 배열 반환 |

---

## 장바구니

| 카테고리 | 메서드 | 엔드포인트 | 설명 | 입력 | 출력 | 예외처리 / 정책 |
|----------|--------|-----------|------|------|------|----------------|
| cart | GET | /cart/{session_id} | 장바구니 조회 | path: `session_id` | `{"items": [{cart_id, menu_id, name, img_url, is_set, drink_option, drink_name, drink_extra_price, side_option, side_name, side_extra_price, quantity, unit_price}], "total": 0}` | 비어있으면 items=[] |
| cart | POST | /cart | 장바구니 담기 | body: `{session_id, menu_id, is_set, drink_option, side_option, quantity, unit_price}` | `{"cart_id": 1, "message": "장바구니에 담겼습니다."}` | 없는 menu_id → 404 / quantity < 1 → 400 / unit_price 미입력 시 DB에서 자동 설정 / 동일 메뉴 담기 시 수량 증가 |
| cart | PUT | /cart/{cart_id} | 수량 직접 수정 | path: `cart_id`, body: `{quantity}` | `{"message": "수량이 수정됐습니다."}` | quantity < 1 → 400 |
| cart | PATCH | /cart/{cart_id}/increase | 수량 +1 | path: `cart_id` | `{"message": "수량이 증가됐습니다."}` | - |
| cart | PATCH | /cart/{cart_id}/decrease | 수량 -1 | path: `cart_id` | `{"message": "수량이 감소됐습니다."}` | 수량 1이면 자동 삭제 |
| cart | DELETE | /cart/{cart_id} | 항목 삭제 | path: `cart_id` | `{"message": "삭제됐습니다."}` | - |
| cart | DELETE | /cart/session/{session_id} | 전체 비우기 | path: `session_id` | `{"message": "장바구니가 비워졌습니다."}` | - |

---

## 주문

| 카테고리 | 메서드 | 엔드포인트 | 설명 | 입력 | 출력 | 예외처리 / 정책 |
|----------|--------|-----------|------|------|------|----------------|
| order | POST | /order | 주문 생성 | body: `{session_id, payment_method}` | `{"order_id": 1, "total_price": 15000, "message": "주문이 생성됐습니다."}` | 장바구니 비어있음 → 400 |
| order | POST | /order/{order_id}/payment | 결제 완료 | path: `order_id`, body: `{session_id}` | `{"message": "결제가 완료됐습니다.", "order_id": 1}` | 없는 order_id → 404 / 이미 결제된 주문 → 400 / 결제 완료 후 장바구니 자동 비워짐 |
| order | GET | /order/{session_id} | 주문 내역 조회 | path: `session_id` | `{"orders": [{order_id, session_id, total_price, payment_method, status, created_at}]}` | 없으면 빈 배열 반환 |

---

## RAG 검색

| 카테고리 | 메서드 | 엔드포인트 | 설명 | 입력 | 출력 | 예외처리 / 정책 |
|----------|--------|-----------|------|------|------|----------------|
| search | POST | /search | 자연어 메뉴 검색 | body: `{query, k, score_threshold}` | `{"query": "...", "results": [{menu_id, name, score, content}]}` | 욕설 포함 → 400 / score_threshold 초과 결과 필터링 |

---

## 헬스체크

| 카테고리 | 메서드 | 엔드포인트 | 설명 | 입력 | 출력 | 예외처리 / 정책 |
|----------|--------|-----------|------|------|------|----------------|
| health | GET | /health | 서버 상태 확인 | - | `{"status": "ok"}` | - |

---

## 공통 정책

| 항목 | 내용 |
|------|------|
| 욕설 필터링 | 모든 POST 요청의 text/query/message 필드에 욕설 감지 시 즉시 400 반환 (LLM 호출 없음) |
| WebSocket 욕설 필터링 | refined_text 에이전트 전달 전 욕설 감지 시 에이전트 호출 없이 음성 응답 반환 |
| 응답 형식 | 모든 응답은 JSON |
| 서버 실행 | `python -m uvicorn api.main:app --reload` |
| Swagger UI | http://127.0.0.1:8000/docs |