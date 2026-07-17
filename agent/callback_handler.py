import json
import time
import uuid
from collections import defaultdict
from langchain.callbacks.base import BaseCallbackHandler


class ExecutionTraceHandler(BaseCallbackHandler):
    """Writes a JSONL execution trace. Every tool-start/end pair shares a
    correlation_id so the governance trace can be joined on that key."""

    def __init__(self, run_id: str, log_path: str = "logs/execution_trace.jsonl"):
        self.run_id = run_id
        self.log_path = log_path
        self._pending: dict[int, str] = {}
        self._call_counter = defaultdict(int)

    def correlation_id_for(self, tool_name: str) -> str:
        key = self._call_counter[tool_name] - 1
        return self._pending.get(key, str(uuid.uuid4()))

    def _write(self, record: dict):
        record["run_id"] = self.run_id
        record["timestamp"] = time.time()
        with open(self.log_path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def on_tool_start(self, serialized, input_str, **kwargs):
        cid = str(uuid.uuid4())
        serial = self._call_counter[serialized.get("name", "")]
        self._call_counter[serialized.get("name", "")] += 1
        self._pending[serial] = cid
        self._write({
            "event": "tool_start",
            "tool": serialized.get("name"),
            "input": input_str,
            "correlation_id": cid,
        })

    def on_tool_end(self, output, **kwargs):
        tool_name = kwargs.get("name", list(self._call_counter.keys())[-1] if self._call_counter else "unknown")
        serial = self._call_counter[tool_name] - 1
        cid = self._pending.get(serial, str(uuid.uuid4()))
        self._write({
            "event": "tool_end",
            "tool": tool_name,
            "output": str(output),
            "correlation_id": cid,
        })

    def on_agent_action(self, action, **kwargs):
        self._write({
            "event": "agent_action",
            "tool": action.tool,
            "tool_input": action.tool_input,
            "log": action.log,
            "correlation_id": str(uuid.uuid4()),
        })
