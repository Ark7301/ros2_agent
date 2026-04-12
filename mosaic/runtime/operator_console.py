from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


class OperatorConsoleState:
    """In-memory bridge between MOSAIC and the operator console UI."""

    def __init__(self) -> None:
        self.current_step: dict[str, Any] | None = None
        self._futures: dict[str, asyncio.Future[Any]] = {}
        self._lock = threading.Lock()

    def publish_step(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self.current_step = payload
            step_id = payload.get("step_id")
            if step_id and step_id in self._futures:
                del self._futures[step_id]

    def submit_result(self, payload: dict[str, Any]) -> None:
        step_id = payload.get("step_id")
        if not step_id:
            return
        with self._lock:
            future = self._futures.pop(step_id, None)
            self.current_step = None
        if not future:
            return
        loop = future.get_loop()
        if loop.is_running():
            loop.call_soon_threadsafe(future.set_result, payload)
        else:
            future.set_result(payload)

    async def wait_for_result(self, step_id: str, timeout_s: float) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        with self._lock:
            self._futures[step_id] = future
        try:
            result = await asyncio.wait_for(future, timeout=timeout_s)
            return result
        finally:
            with self._lock:
                existing = self._futures.get(step_id)
                if existing is future:
                    del self._futures[step_id]


def _build_handler(state: OperatorConsoleState) -> type[BaseHTTPRequestHandler]:
    class OperatorHandler(BaseHTTPRequestHandler):
        """HTTP handler for the operator console UI."""

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _set_json_headers(self, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()

        def _respond_json(self, payload: Any, status: int = 200) -> None:
            self._set_json_headers(status)
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                html = (
                    "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Operator Console</title>"
                    "<style>body{font-family:system-ui, sans-serif;padding:2rem;background:#10121a;color:#f5f5f5;}"
                    "label{display:block;margin-top:0.75rem;font-weight:600;}"
                    "textarea,input{text-transform:none;width:100%;box-sizing:border-box;padding:0.5rem;margin-top:0.25rem;}"
                    "button{margin-top:1rem;padding:0.75rem 1.25rem;border:none;border-radius:0.375rem;background:#3b82f6;color:white;font-weight:600;cursor:pointer;}</style>"
                    "</head><body><h1>Operator Console</h1>"
                    "<p>Current step details:</p><pre id='step-json' style='background:#111827;padding:1rem;border-radius:0.5rem;min-height:120px;overflow:auto;'></pre>"
                    "<form id='submission-form'><label>Operator Result<input name='operator_result' value='completed'></label>"
                    "<label>Front Image Path<input name='front' placeholder='front.jpg'></label>"
                    "<label>Left Image Path<input name='left' placeholder='left.jpg'></label>"
                    "<label>Right Image Path<input name='right' placeholder='right.jpg'></label>"
                    "<label>Back Image Path<input name='back' placeholder='back.jpg'></label>"
                    "<input type='hidden' name='step_id'><button type='submit'>Submit Result</button></form>"
                    "<script>const form=document.getElementById('submission-form');const stepJson=document.getElementById('step-json');"
                    "async function refreshStep(){const resp=await fetch('/step');const data=await resp.json();stepJson.textContent=JSON.stringify(data,null,2);"
                    "form.step_id.value=data.step_id||'';}refreshStep();setInterval(refreshStep,1500);"
                    "form.addEventListener('submit',async ev=>{ev.preventDefault();const formData=new FormData(form);const payload={step_id:formData.get('step_id'),operator_result:formData.get('operator_result'),images:{front:formData.get('front'),left:formData.get('left'),right:formData.get('right'),back:formData.get('back')},timestamp:Date.now()/1000};"
                    "await fetch('/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});alert('Result submitted.');});</script></body></html>"
                )
                self.wfile.write(html.encode("utf-8"))
                return

            if parsed.path == "/step":
                self._respond_json(state.current_step or {})
                return

            self.send_error(404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/submit":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body.decode("utf-8"))
            except ValueError:
                self.send_error(400, "Invalid JSON")
                return
            state.submit_result(payload)
            self.send_response(204)
            self.end_headers()

    return OperatorHandler


class OperatorConsoleServer:
    """Local HTTP server that exposes the human proxy operator console."""

    def __init__(self, state: OperatorConsoleState, host: str = "127.0.0.1", port: int = 8766) -> None:
        self._state = state
        self._host = host
        self._port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server:
            return
        handler = _build_handler(self._state)
        self._server = ThreadingHTTPServer((self._host, self._port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._server:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._server = None
        self._thread = None
