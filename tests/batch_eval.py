"""
배치 평가 스크립트 - 320개 녹음 파일 대상 STT 정확도 + 파이프라인 속도 + Agent 정확도 측정

파일 명명 규칙:
  조용한 환경: {speaker}_{id}.m4a      예) sh_1.m4a  sb_12.m4a
  소음 환경  : n_{speaker}_{id}.m4a   예) n_sh_1.m4a  n_br_12.m4a
  speaker: sh / sb / br / hn  |  id: 1 ~ 40

세션 그룹 (Agent 테스트):
  1~10  : 화자+환경 조합당 하나의 연속 세션 (직접주문 흐름)
  11~20 : 대사마다 독립 세션 (메뉴 검색, 문맥 독립)
  21~30 : 화자+환경 조합당 하나의 연속 세션 (엣지케이스 흐름)
  31~35 : 화자+환경 조합당 하나의 연속 세션 (접근성 흐름 1)
  36~40 : 화자+환경 조합당 하나의 연속 세션 (접근성 흐름 2)

실행 예:
  python tests/batch_eval.py --audio-dir recordings --phase stt
  python tests/batch_eval.py --audio-dir recordings --phase pipeline
  python tests/batch_eval.py --audio-dir recordings --phase all
  python tests/batch_eval.py --audio-dir recordings --phase pipeline --speaker sh --env quiet
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ─── 정답 텍스트 (40개 스크립트) ──────────────────────────────────────────
GROUND_TRUTH: dict[int, str] = {
    1:  "리아 불고기버거 하나 줘",
    2:  "치킨버거 2개 담아줘",
    3:  "통다리 크리스피치킨버거 세트로 담아주고, 음료는 사이다로",
    4:  "데리버거 1개 담아줘",
    5:  "치킨버거 2개 더 추가해줘",
    6:  "한우불고기 버거 3개로 바꿔줘",
    7:  "데리버거 하나 빼줘",
    8:  "장바구니 확인해줘",
    9:  "총 얼마야?",
    10: "주문 완료해줘",
    11: "소고기 안 들어가는 버거 추천해줘.",
    12: "신메뉴 먹고싶어.",
    13: "가장 인기있는 메뉴가 뭐야?",
    14: "칼로리 낮은 메뉴 추천해줘.",
    15: "유제품 못 먹는데 괜찮은 메뉴 추천해줘.",
    16: "단백질 높은 버거가 뭐야?",
    17: "해산물 알레르기 있는데 먹을 수 있는 메뉴 추천해줘.",
    18: "여기 베스트 메뉴가 뭐야?",
    19: "치즈 안 들어가는 버거 알려줘.",
    20: "가장 저렴한 사이드 메뉴 추천해줘.",
    21: "불고기 패티 들어간 버거 추천해줘",
    22: "첫번째 거를 세트로 콜라랑 감튀 담아줘",
    23: "응",
    24: "리아 새우도 단품으로 하나줘",
    25: "처음에 주문한것도 단품으로 하고 싶어.",
    26: "국밥도 한그릇 주라.",
    27: "왜 안주는데 시발",
    28: "그러면 사장님 번호라도 주라.",
    29: "갑자기 먹기 싫네 싹 다 취소해줘.",
    30: "총 얼마야?",
    31: "나 시각장애가 있는데 메뉴를 소리로 읽어줄 수 있어?",
    32: "추천메뉴 알려줘",
    33: "방금 화면에 뭔가 나온 것 같은데, 뭐라고 써 있어?",
    34: "지금까지 주문 어떻게 됐는지 다 읽어줘",
    35: "지금 무슨 단계야?",
    36: "직원은 없어? 기계한테 말하니까 이상한데",
    37: "뭐가 이리 복잡해. 그냥 햄버거 하나 줘",
    38: "제일 많이 팔리는 거 하나 줘",
    39: "비싸네. 이거 돈좀 깎아줄 수 없나?",
    40: "그거…. 데리버거… 하나줘봐",
}

# ─── 기대 Action 레이블 ───────────────────────────────────────────────────
EXPECTED_ACTIONS: dict[int, str] = {
    1:  "TYPE_SELECT:119",
    2:  "CART_ADD",
    3:  "CART_ADD",
    4:  "CART_ADD",
    5:  "CART_ADD",
    6:  "NONE",
    7:  "NONE",
    8:  "PAGE:cart",
    9:  "NONE",
    10: "NONE",
    11: "RECOMMEND",
    12: "RECOMMEND",
    13: "TYPE_SELECT:106",
    14: "NONE",
    15: "RECOMMEND",
    16: "NONE",
    17: "RECOMMEND",
    18: "TYPE_SELECT:106",
    19: "RECOMMEND",
    20: "NONE",
    21: "RECOMMEND",
    22: "CART_ADD",
    23: "NONE",
    24: "CART_ADD",
    25: "NONE",
    26: "NONE",
    27: "NONE",
    28: "NONE",
    29: "NONE",
    30: "NONE",
    31: "NONE",
    32: "RECOMMEND",
    33: "RECOMMEND",
    34: "NONE",
    35: "NONE",
    36: "NONE",
    37: "TAB:버거",
    38: "TYPE_SELECT:106",
    39: "NONE",
    40: "TYPE_SELECT:123",
}

SCRIPT_CATEGORY: dict[int, str] = {
    **{i: "직접주문"  for i in range(1,  11)},
    **{i: "메뉴검색"  for i in range(11, 21)},
    **{i: "엣지케이스" for i in range(21, 31)},
    **{i: "접근성"    for i in range(31, 41)},
}

# 세션 그룹
SESSION_GROUP: dict[int, str] = {
    **{i: "ordering" for i in range(1,  11)},
    **{i: None       for i in range(11, 21)},  # 독립 세션
    **{i: "edge"     for i in range(21, 31)},
    **{i: "access1"  for i in range(31, 36)},
    **{i: "access2"  for i in range(36, 41)},
}

# ─── 정답 음성 응답 텍스트 ────────────────────────────────────────────────
EXPECTED_VOICE: dict[int, str] = {
    1:  "리아 불고기버거 단품과 세트 중 어떻게 드릴까요?",
    2:  "치킨버거 2개를 담으시겠습니까?",
    3:  "통다리 크리스피치킨버거 세트(사이다, 포테이토)로 담으시겠습니까?",
    4:  "데리버거 1개를 담으시겠습니까?",
    5:  "치킨버거 2개를 추가로 담으시겠습니까?",
    6:  "장바구니에 한우불고기버거가 들어있지 않습니다.  추가로 필요한 것이 있으신가요?",
    7:  "장바구니에 데리버거가 들어있지 않습니다. 추가로 필요한 것이 있으신가요?",
    8:  "장바구니를 확인해 드릴게요.",
    9:  "현재 장바구니의 총액은 10,400원입니다.",
    10: "주문 내역을 확인해 드릴게요. 카드와 모바일 중 어떻게 결제하시겠어요?",
    11: "더블 치킨버거, 더블 치킨버거(N), NEW 더블 미라클버거 중에서 선택해 주세요.",
    12: "신메뉴로는 통다리 크리스피치킨버거(파이어핫), 통다리 크리스피치킨버거(그릭랜치), 디지게 매운 돈까스(디진다맛)가 있습니다. 어떤 메뉴로 드릴까요?",
    13: "한우불고기버거가 가장 인기 있어요. 브리오쉬번에 국내산 한우를 사용한 패티, 신선한 야채, 특제소스로 완성한 프리미엄 햄버거입니다. 단품과 세트 중 어떻게 드릴까요?",
    14: "칼로리가 낮은 메뉴로는 제로슈거콜라 2,000원, 아이스 아메리카노 2,500원, 아메리카노 2,500원이 있습니다. 추가로 필요한 것이 있으신가요?",
    15: "유제품이 없는 메뉴로는 NEW 미라클버거, NEW 더블 미라클버거, 포테이토가 있습니다. NEW 미라클버거는 100% 식물성 패티와 신선한 야채들이 조화된 대체육버거로 5,700원입니다. 추가로 필요한 것이 있으신가요?",
    16: "단백질이 높은 버거는 더블 한우불고기버거, 리아 불고기 더블(빅불), 모짜렐라 인 더 버거 베이컨입니다. 더블 한우불고기버거는 13,000원이고, 국내산 한우를 사용한 패티 2장 구성으로 육즙 가득한 프리미엄 버거입니다. 리아 불고기 더블(빅불)은 7,600원으로 불고기 특유의 소스와 쇠고기의 진함을 배로 느낄 수 있는 제품입니다. 모짜렐라 인 더 버거 베이컨은 8,000원으로 자연산 모짜렐라 치즈와 고소한 베이컨이 만나 풍부한 맛을 제공합니다.",
    17: "한우불고기버거, 리아 불고기, 통다리 크리스피치킨버거(파이어핫)를 추천드려요. 한우불고기버거는 브리오쉬번에 국내산 한우를 사용한 패티와 신선한 야채, 특제소스로 완성한 프리미엄 햄버거입니다. 리아 불고기는 두툼한 쇠고기패티와 한국적인 맛의 소스가 잘 조화된 롯데리아 대표 버거입니다. 통다리 크리스피치킨버거(파이어핫)는 육즙 가득 통다리살에 버터밀크 외피로 입안을 가득 채우는 바삭함이 특징이며, 중독성 있는 갈릭핫소스로 강렬한 매운맛을 자랑합니다. 어떤 걸로 드릴까요?",
    18: "한우불고기버거가 가장 인기 있어요. 브리오쉬번에 국내산 한우를 사용한 패티, 신선한 야채, 특제소스로 완성한 프리미엄 햄버거입니다. 단품과 세트 중 어떻게 드릴까요?",
    19: "치즈가 들어가지 않는 버거로는 한우불고기버거 9,000원, 리아 불고기 5,000원이 있습니다. 어떤 것을 선택하시겠어요?",
    20: "가장 저렴한 사이드 메뉴는 코울슬로로, 1,900원입니다.",
    21: "리아 불고기, 한우불고기버거, 더블 한우불고기버거 중에서 선택해 주세요.",
    22: "주문 내역을 확인해주세요. 담으시겠습니까?",
    23: "리아 불고기를 담았습니다. 추가로 필요한 것이 있으신가요?",
    24: "리아 새우를 단품으로 담으시겠습니까?",
    25: "리아 불고기를 단품으로 변경했습니다. 추가로 필요한 것이 있으신가요?",
    26: "죄송하지만, 국밥은 제공하지 않습니다. 다른 메뉴를 선택해 주세요.",
    27: "죄송합니다. 리아버거에서는 국밥을 제공하지 않습니다. 다른 메뉴를 도와드릴 수 있습니다.",
    28: "저는 주문을 도와드리는 AI 도우미입니다. 편하게 말씀해 주세요!",
    29: "장바구니를 비웠습니다. 추가로 필요한 것이 있으신가요?",
    30: "장바구니가 비어 있습니다.",
    31: "네, 메뉴를 읽어드릴게요. 버거·디저트·치킨·음료 중 어떤 카테고리를 들으시겠어요?",
    32: "추천 메뉴를 알려드릴게요. 한우불고기버거 9,000원, 리아 불고기 5,000원, 통다리 크리스피치킨버거(파이어핫) 6,900원입니다. 어떤 메뉴로 도와드릴까요?",
    33: "추천 메뉴로 한우불고기버거 9,000원, 리아 불고기 5,000원, 통다리 크리스피치킨버거(파이어핫) 6,900원이 있습니다. 어떤 메뉴로 도와드릴까요?",
    34: "현재 장바구니가 비어 있습니다. 추가로 주문하실 메뉴가 있으신가요?",
    35: "현재 주문 단계입니다. 원하시는 메뉴 이름을 말씀해 주시면 장바구니에 담아드립니다.",
    36: "저는 주문을 도와드리는 AI 도우미입니다. 편하게 말씀해 주세요!",
    37: "버거 메뉴를 보여드릴게요.",
    38: "한우불고기버거가 가장 인기 있어요. 브리오쉬번에 국내산 한우를 사용한 패티, 신선한 야채, 특제소스로 완성한 프리미엄 햄버거. 단품과 세트 중 어떻게 드릴까요?",
    39: "죄송하지만 가격은 고정되어 있어 할인은 어렵습니다. 다른 메뉴를 추천해드릴까요?",
    40: "데리버거를 단품과 세트 중 어떻게 드릴까요?",
}


# ─── 파일명 파서 ──────────────────────────────────────────────────────────
FILENAME_QUIET = re.compile(r"^(?P<speaker>sh|sb|br|hn)_(?P<id>\d+)\.m4a$", re.IGNORECASE)
FILENAME_NOISY = re.compile(r"^n_(?P<speaker>sh|sb|br|hn)_(?P<id>\d+)\.m4a$", re.IGNORECASE)


def parse_filename(path: Path) -> dict | None:
    m = FILENAME_NOISY.match(path.name)
    if m:
        return {"path": path, "speaker": m.group("speaker").lower(),
                "env": "noisy", "id": int(m.group("id"))}
    m = FILENAME_QUIET.match(path.name)
    if m:
        return {"path": path, "speaker": m.group("speaker").lower(),
                "env": "quiet", "id": int(m.group("id"))}
    return None


# ─── CER ─────────────────────────────────────────────────────────────────
def _edit_distance(a: str, b: str) -> int:
    dp = list(range(len(b) + 1))
    for ca in a:
        ndp = [dp[0] + 1]
        for j, cb in enumerate(b):
            ndp.append(min(dp[j] + (ca != cb), dp[j + 1] + 1, ndp[-1] + 1))
        dp = ndp
    return dp[-1]


def cer(reference: str, hypothesis: str) -> float:
    ref = reference.replace(" ", "")
    hyp = hypothesis.replace(" ", "")
    if not ref:
        return 0.0
    return _edit_distance(ref, hyp) / len(ref)


# ─── Action 유틸 ─────────────────────────────────────────────────────────
_ID_PREFIXES = {"TYPE_SELECT", "DRINK_SELECT", "SIDE_SELECT"}


def extract_action(text: str) -> str:
    """에이전트 JSON 응답에서 action 필드 추출"""
    try:
        data = json.loads(text)
        return data.get("action", "NONE") or "NONE"
    except Exception:
        return "NONE"


def _action_prefix(action: str) -> str:
    prefix = action.split(":")[0]
    return prefix if prefix in _ID_PREFIXES else action


def action_type_ok(script_id: int, actual: str) -> bool:
    """관대한 비교: TYPE_SELECT:119 기대 시 TYPE_SELECT:107 이어도 ✓"""
    expected = EXPECTED_ACTIONS.get(script_id, "NONE")
    return _action_prefix(actual) == _action_prefix(expected)


def action_full_ok(script_id: int, actual: str) -> bool:
    """엄격한 비교: TYPE_SELECT:119 기대 시 TYPE_SELECT:107 이면 ✗"""
    expected = EXPECTED_ACTIONS.get(script_id, "NONE")
    return actual == expected


# ─── 음성 응답 추출 + 임베딩 유사도 ──────────────────────────────────────
def extract_voice(agent_response: str) -> str:
    """에이전트 JSON 응답에서 voice 필드 추출"""
    try:
        data = json.loads(agent_response)
        return data.get("voice", "") or ""
    except Exception:
        return agent_response.strip()


def _cosine(a: list[float], b: list[float]) -> float:
    dot  = sum(x * y for x, y in zip(a, b))
    na   = sum(x * x for x in a) ** 0.5
    nb   = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """OpenAI text-embedding-3-small으로 배치 임베딩"""
    import openai
    client = openai.OpenAI()
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]


def precompute_expected_embeddings() -> dict[int, list[float]]:
    """40개 정답 음성 텍스트를 한 번에 임베딩해 반환"""
    ids   = list(EXPECTED_VOICE.keys())
    texts = [EXPECTED_VOICE[i] for i in ids]
    print(f"[임베딩] 정답 {len(texts)}개 사전 계산 중...")
    vecs  = get_embeddings(texts)
    print("[임베딩] 완료")
    return dict(zip(ids, vecs))


def voice_similarity(script_id: int, actual_voice: str,
                     expected_embs: dict[int, list[float]]) -> float | None:
    if not actual_voice.strip() or script_id not in expected_embs:
        return None
    actual_emb = get_embeddings([actual_voice])[0]
    return round(_cosine(expected_embs[script_id], actual_emb), 4)


# ─── Phase 1: STT 단독 ───────────────────────────────────────────────────
def run_stt_phase(recordings: list[dict], model) -> list[dict]:
    from voice.stt import transcribe

    results = []
    for i, rec in enumerate(recordings, 1):
        ref = GROUND_TRUTH.get(rec["id"], "")
        t0 = time.time()
        try:
            hyp = transcribe(model, str(rec["path"]))
        except Exception as e:
            hyp = ""
            print(f"  [ERROR] {rec['path'].name}: {e}")
        stt_ms = round((time.time() - t0) * 1000)
        c = cer(ref, hyp)

        row = {
            **{k: rec[k] for k in ("speaker", "env", "id", "path")},
            "category": SCRIPT_CATEGORY.get(rec["id"], ""),
            "ref": ref, "hyp": hyp,
            "cer": round(c, 4), "stt_ms": stt_ms,
        }
        results.append(row)
        print(f"[{i:3}/{len(recordings)}] {rec['path'].name}  CER={c:.2%}  {stt_ms}ms")
        print(f"  REF: {ref}")
        print(f"  HYP: {hyp}")

    return results


# ─── Phase 2+3: 파이프라인 ────────────────────────────────────────────────
def run_pipeline_phase(recordings: list[dict], model, agent_delay: float = 10.0) -> list[dict]:
    from voice.stt import transcribe
    from app.agent import chat, clear_history
    from db.sqlite import clear_cart

    expected_embs = precompute_expected_embeddings()

    combos: dict[tuple, list] = {}
    for rec in recordings:
        key = (rec["speaker"], rec["env"])
        combos.setdefault(key, []).append(rec)
    for key in combos:
        combos[key].sort(key=lambda r: r["id"])

    results: list[dict] = []
    total = len(recordings)
    done = 0

    for (speaker, env), recs in sorted(combos.items()):
        active_sessions: dict[str, str] = {}

        for rec in recs:
            script_id = rec["id"]
            group = SESSION_GROUP.get(script_id)

            if group is None:
                session_id = f"eval_{speaker}_{env}_{script_id:03d}_ind"
                clear_history(session_id)
                clear_cart(session_id)
            else:
                if group not in active_sessions:
                    sid = f"eval_{speaker}_{env}_{group}"
                    active_sessions[group] = sid
                    clear_history(sid)
                    clear_cart(sid)
                session_id = active_sessions[group]

            ref = GROUND_TRUTH.get(script_id, "")

            t0 = time.time()
            try:
                hyp = transcribe(model, str(rec["path"]))
            except Exception as e:
                hyp = ""
                print(f"  [STT ERROR] {rec['path'].name}: {e}")
            stt_ms = round((time.time() - t0) * 1000)

            actual_action, agent_ms, llm_ms, tool_ms, response = "", 0, 0, 0, ""
            actual_voice, vsim, tts_ms = "", None, 0
            if hyp.strip():
                time.sleep(agent_delay)
                import openai as _openai
                for _attempt in range(1, 6):
                    try:
                        t1 = time.time()
                        response, latency = chat(hyp.strip(), session_id)
                        agent_ms = round((time.time() - t1) * 1000)
                        llm_ms   = latency.get("llm_total_ms", 0)
                        tool_ms  = latency.get("tool_total_ms", 0)
                        actual_action = extract_action(response)
                        actual_voice  = extract_voice(response)
                        vsim = voice_similarity(script_id, actual_voice, expected_embs)
                        break
                    except _openai.RateLimitError as e:
                        _m = re.search(r"try again in (\d+(?:\.\d+)?)(ms|s)", str(e))
                        _wait = (float(_m.group(1)) / 1000 if _m and _m.group(2) == "ms"
                                 else float(_m.group(1)) if _m else 60.0) + 1.0
                        print(f"  [429] {_wait:.1f}s 대기 후 재시도 ({_attempt}/5)")
                        time.sleep(_wait)
                    except Exception as e:
                        print(f"  [AGENT ERROR] {rec['path'].name}: {e}")
                        break

            if actual_voice.strip():
                from voice.tts import synthesize
                t_tts = time.time()
                try:
                    synthesize(actual_voice)
                except Exception as e:
                    print(f"  [TTS ERROR] {e}")
                tts_ms = round((time.time() - t_tts) * 1000)

            if group is None:
                clear_history(session_id)

            type_ok = action_type_ok(script_id, actual_action) if hyp.strip() else None
            full_ok = action_full_ok(script_id, actual_action) if hyp.strip() else None
            mark = "✓" if full_ok is True else ("△" if type_ok is True else ("✗" if type_ok is False else "-"))

            row = {
                "speaker": speaker, "env": env, "id": script_id,
                "category": SCRIPT_CATEGORY.get(script_id, ""),
                "session_group": group or "independent",
                "ref": ref, "hyp": hyp,
                "cer": round(cer(ref, hyp), 4),
                "stt_ms": stt_ms,
                "expected_action": EXPECTED_ACTIONS.get(script_id, ""),
                "actual_action": actual_action,
                "action_type_ok": type_ok,
                "action_full_ok": full_ok,
                "expected_voice": EXPECTED_VOICE.get(script_id, ""),
                "actual_voice": actual_voice,
                "voice_sim": vsim,
                "agent_ms": agent_ms,
                "llm_ms": llm_ms,
                "tool_ms": tool_ms,
                "tts_ms": tts_ms,
                "total_ms": stt_ms + agent_ms + tts_ms,
                "response_head": response[:200],
            }
            results.append(row)
            done += 1
            print(
                f"[{done:3}/{total}] {rec['path'].name}"
                f"  CER={row['cer']:.2%}  STT={stt_ms}ms"
                f"  Agent={agent_ms}ms  {mark}"
                f"  ({actual_action})"
            )

        for sid in active_sessions.values():
            clear_history(sid)

    return results


# ─── 요약 출력 ────────────────────────────────────────────────────────────
def summarize(results: list[dict], measure_agent: bool):
    def avg(vals):
        v = [x for x in vals if x is not None]
        return sum(v) / len(v) if v else 0.0

    print("\n" + "=" * 64)
    print("■ 전체 요약")
    print(f"  파일 수   : {len(results)}")
    print(f"  평균 CER  : {avg(r['cer'] for r in results):.2%}")
    print(f"  평균 STT  : {avg(r['stt_ms'] for r in results):.0f}ms")

    if measure_agent:
        scored = [r for r in results if r.get("action_type_ok") is not None]
        if scored:
            t_ok = sum(1 for r in scored if r["action_type_ok"])
            f_ok = sum(1 for r in scored if r["action_full_ok"])
            print(f"  Action 정확도 (관대): {t_ok}/{len(scored)}  ({t_ok/len(scored):.1%})  — 타입만 일치")
            print(f"  Action 정확도 (엄격): {f_ok}/{len(scored)}  ({f_ok/len(scored):.1%})  — 타입+ID 일치")
        vsim_vals = [r["voice_sim"] for r in results if r.get("voice_sim") is not None]
        if vsim_vals:
            print(f"  응답 유사도 (평균)  : {sum(vsim_vals)/len(vsim_vals):.4f}  — 코사인 유사도 0~1")
        print(f"  평균 Agent : {avg(r['agent_ms'] for r in results):.0f}ms")
        print(f"  평균 TTS   : {avg(r.get('tts_ms', 0) for r in results):.0f}ms")
        print(f"  평균 Total : {avg(r['total_ms'] for r in results):.0f}ms")

    for dim, key in [("화자", "speaker"), ("환경", "env"), ("카테고리", "category")]:
        print(f"\n■ {dim}별")
        groups: dict[str, list] = {}
        for r in results:
            groups.setdefault(r[key], []).append(r)
        for grp, items in sorted(groups.items()):
            line = (
                f"  {grp:14}"
                f"  CER={avg(r['cer'] for r in items):.2%}"
                f"  STT={avg(r['stt_ms'] for r in items):.0f}ms"
            )
            if measure_agent:
                sc = [r for r in items if r.get("action_type_ok") is not None]
                if sc:
                    t_ok = sum(1 for r in sc if r["action_type_ok"])
                    f_ok = sum(1 for r in sc if r["action_full_ok"])
                    vs = [r["voice_sim"] for r in items if r.get("voice_sim") is not None]
                    vsim_str = f"  유사도={sum(vs)/len(vs):.3f}" if vs else ""
                    line += f"  관대={t_ok/len(sc):.1%}  엄격={f_ok/len(sc):.1%}{vsim_str}  Agent={avg(r['agent_ms'] for r in items):.0f}ms  TTS={avg(r.get('tts_ms',0) for r in items):.0f}ms"
            print(line)


# ─── CSV 저장 ─────────────────────────────────────────────────────────────
def save_csv(results: list[dict], out_path: Path):
    if not results:
        return
    rows = [{k: v for k, v in r.items() if k != "path"} for r in results]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n[저장] {out_path}")


# ─── 메인 ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="배치 평가 스크립트")
    parser.add_argument("--audio-dir",   default="tests/recordings")
    parser.add_argument("--phase",       choices=["stt", "pipeline", "all"], default="stt")
    parser.add_argument("--model-size",  default="small")
    parser.add_argument("--out-dir",     default="tests/results")
    parser.add_argument("--speaker",     help="특정 화자만 (sh/sb/br/hn)")
    parser.add_argument("--env",         help="특정 환경만 (quiet/noisy)")
    parser.add_argument("--limit",       type=int, help="최대 파일 수 (디버깅용)")
    parser.add_argument("--agent-delay", type=float, default=10.0)
    args = parser.parse_args()

    audio_dir = Path(args.audio_dir)
    if not audio_dir.exists():
        print(f"[ERROR] 디렉터리 없음: {audio_dir}")
        sys.exit(1)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    recordings = []
    for p in audio_dir.glob("*.m4a"):
        rec = parse_filename(p)
        if rec is None:
            continue
        if rec["id"] > 40:  # 1~40만 사용
            continue
        if args.speaker and rec["speaker"] != args.speaker:
            continue
        if args.env and rec["env"] != args.env:
            continue
        recordings.append(rec)

    recordings.sort(key=lambda r: (r["speaker"], r["env"], r["id"]))

    if args.limit:
        recordings = recordings[: args.limit]

    print(f"대상 파일: {len(recordings)}개  (model={args.model_size})\n")
    if not recordings:
        print("[ERROR] 처리할 파일 없음")
        sys.exit(1)

    from voice.stt import load_model
    model = load_model(model_size=args.model_size)

    ts = time.strftime("%Y%m%d_%H%M%S")

    if args.phase in ("stt", "all"):
        print("\n─── Phase 1: STT 정확도 ───")
        stt_results = run_stt_phase(recordings, model)
        summarize(stt_results, measure_agent=False)
        save_csv(stt_results, out_dir / f"stt_{ts}.csv")

    if args.phase in ("pipeline", "all"):
        print("\n─── Phase 2+3: 파이프라인 (STT + Agent) ───")
        pipe_results = run_pipeline_phase(recordings, model, agent_delay=args.agent_delay)
        summarize(pipe_results, measure_agent=True)
        save_csv(pipe_results, out_dir / f"pipeline_{ts}.csv")


if __name__ == "__main__":
    main()
