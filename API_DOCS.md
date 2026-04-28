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
| menu | GET | /menu/{id}/set | 세트 조회 | path: `menu_id` | `{"set": {set_id, burger_menu_id, name, set_price, img_url, allergy, origin, calorie}}` | 세트 없음 → 404 |

---

## 장바구니

| 카테고리 | 메서드 | 엔드포인트 | 설명 | 입력 | 출력 | 예외처리 / 정책 |
|----------|--------|-----------|------|------|------|----------------|
| cart | GET | /cart/{session_id} | 장바구니 조회 | path: `session_id` | `{"items": [{cart_id, menu_id, name, img_url, is_set, drink_option, side_option, quantity, unit_price}], "total": 0}` | 비어있으면 items=[] |
| cart | POST | /cart | 장바구니 담기 | body: `{session_id, menu_id, is_set, drink_option, side_option, quantity, unit_price}` | `{"cart_id": 1, "message": "장바구니에 담겼습니다."}` | - |
| cart | PUT | /cart/{cart_id} | 수량 수정 | path: `cart_id`, body: `{quantity}` | `{"message": "수량이 수정됐습니다."}` | quantity < 1 → 400 |
| cart | DELETE | /cart/{cart_id} | 항목 삭제 | path: `cart_id` | `{"message": "삭제됐습니다."}` | - |
| cart | DELETE | /cart/session/{session_id} | 전체 비우기 | path: `session_id` | `{"message": "장바구니가 비워졌습니다."}` | - |

---

## 주문

| 카테고리 | 메서드 | 엔드포인트 | 설명 | 입력 | 출력 | 예외처리 / 정책 |
|----------|--------|-----------|------|------|------|----------------|
| order | POST | /order | 주문 생성 | body: `{session_id, payment_method}` | `{"order_id": 1, "total_price": 15000, "message": "주문이 생성됐습니다."}` | 장바구니 비어있음 → 400 |
| order | POST | /order/{order_id}/payment | 결제 완료 | path: `order_id`, body: `{session_id}` | `{"message": "결제가 완료됐습니다.", "order_id": 1}` | - 결제 완료 후 장바구니 자동 비워짐 |
| order | GET | /order/{session_id} | 주문 내역 조회 | path: `session_id` | `{"orders": [{order_id, session_id, total_price, payment_method, status, created_at}]}` | 없으면 빈 배열 반환 |

---

## 세션

| 카테고리 | 메서드 | 엔드포인트 | 설명 | 입력 | 출력 | 예외처리 / 정책 |
|----------|--------|-----------|------|------|------|----------------|
| session | POST | /session/{session_id} | 세션 생성 | path: `session_id` | `{"session_id": "abc123", "message": "세션이 생성됐습니다."}` | 이미 존재하면 무시 (INSERT OR IGNORE) |
| session | GET | /session/{session_id} | 세션 조회 | path: `session_id` | `{session_id, current_state, last_recommended, updated_at}` | 없는 세션 → 404 |
| session | PUT | /session/{session_id} | 세션 업데이트 | path: `session_id`, body: `{current_state, last_recommended}` | `{"message": "세션이 업데이트됐습니다."}` | - |

---

## RAG 검색

| 카테고리 | 메서드 | 엔드포인트 | 설명 | 입력 | 출력 | 예외처리 / 정책 |
|----------|--------|-----------|------|------|------|----------------|
| search | POST | /search | 자연어 메뉴 검색 | body: `{query, k, score_threshold}` | `{"query": "...", "results": [{menu_id, name, score, content}]}` | 욕설 포함 → 400 / score_threshold 초과 결과 필터링 |

---

## 공통 정책

| 항목 | 내용 |
|------|------|
| 욕설 필터링 | 모든 POST 요청의 text/query/message 필드에 욕설 감지 시 즉시 400 반환 |
| 응답 형식 | 모든 응답은 JSON |
| 서버 실행 | `python -m uvicorn api.main:app --reload` |
| Swagger UI | http://127.0.0.1:8000/docs |