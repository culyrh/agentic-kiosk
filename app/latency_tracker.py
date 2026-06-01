import time
from langchain_core.callbacks.base import BaseCallbackHandler


class LatencyTracker(BaseCallbackHandler):
    def __init__(self):
        self.log: list[dict] = []
        self._llm_start: float | None = None
        self._tool_starts: dict[str, tuple[str, float]] = {}

    # ── 직접 호출용 (astream_events 이벤트에서 chat_stream이 직접 호출) ──

    def record_llm_start(self):
        self._llm_start = time.time()

    def record_llm_end(self):
        if self._llm_start is not None:
            self.log.append({"type": "llm", "ms": round((time.time() - self._llm_start) * 1000)})
            self._llm_start = None

    def record_tool_start(self, run_id: str, name: str):
        self._tool_starts[run_id] = (name, time.time())

    def record_tool_end(self, run_id: str):
        name, start = self._tool_starts.pop(run_id, ("unknown", time.time()))
        self.log.append({"type": "tool", "name": name, "ms": round((time.time() - start) * 1000)})

    # ── 콜백용 (sync agent.invoke() → chat() 경로) ──

    def on_llm_start(self, serialized, messages, **kwargs):
        self.record_llm_start()

    def on_llm_end(self, response, **kwargs):
        self.record_llm_end()

    def on_tool_start(self, serialized, input_str, run_id, **kwargs):
        self.record_tool_start(str(run_id), serialized.get("name", "unknown"))

    def on_tool_end(self, output, run_id, **kwargs):
        self.record_tool_end(str(run_id))

    def summary(self) -> dict:
        llm_total = sum(e["ms"] for e in self.log if e["type"] == "llm")
        tool_total = sum(e["ms"] for e in self.log if e["type"] == "tool")
        tool_calls = [{"name": e["name"], "ms": e["ms"]} for e in self.log if e["type"] == "tool"]
        return {
            "llm_total_ms": llm_total,
            "tool_total_ms": tool_total,
            "llm_calls": sum(1 for e in self.log if e["type"] == "llm"),
            "tool_calls": tool_calls,
            "detail": self.log,
        }
