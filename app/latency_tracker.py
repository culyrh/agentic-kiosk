import time
from langchain_core.callbacks.base import BaseCallbackHandler


class LatencyTracker(BaseCallbackHandler):
    def __init__(self):
        self.log: list[dict] = []
        self._llm_start: float | None = None
        self._tool_starts: dict[str, tuple[str, float]] = {}

    def on_llm_start(self, serialized, messages, **kwargs):
        self._llm_start = time.time()

    def on_llm_end(self, response, **kwargs):
        if self._llm_start is not None:
            self.log.append({"type": "llm", "ms": round((time.time() - self._llm_start) * 1000)})
            self._llm_start = None

    def on_tool_start(self, serialized, input_str, run_id, **kwargs):
        self._tool_starts[str(run_id)] = (serialized.get("name", "unknown"), time.time())

    def on_tool_end(self, output, run_id, **kwargs):
        name, start = self._tool_starts.pop(str(run_id), ("unknown", time.time()))
        self.log.append({"type": "tool", "name": name, "ms": round((time.time() - start) * 1000)})

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
