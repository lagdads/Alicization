"""本地 Web UI：编辑配置并运行演示。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "web"

PERSONA_DIR = ROOT / "data/personas"
BASE_CONFIGS: Dict[str, Dict[str, Path]] = {
    "llm_config": {"label": "LLM 配置", "path": ROOT / "data/llm_config.json"},
    "knowledge_graph": {
        "label": "知识树",
        "path": ROOT / "data/knowledge_graph.json",
    },
}

MAX_RUN_SECONDS = 20
MAX_OUTPUT_CHARS = 12000


def _read_text(path: Path) -> str:
    """读取文本文件内容。"""
    with path.open("r", encoding="utf-8") as handle:
        return handle.read()


def _write_json_pretty(path: Path, raw_text: str) -> None:
    """将 JSON 文本写为格式化文件。"""
    data = json.loads(raw_text)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _normalize_persona_filename(raw_name: str) -> str:
    """规范化人设文件名并校验合法性。"""
    name = raw_name.strip()
    if not name:
        raise ValueError("人设文件名不能为空")
    if name.endswith(".json"):
        base = name[: -len(".json")]
    else:
        base = name
    if not re.fullmatch(r"[A-Za-z0-9_-]+", base):
        raise ValueError("人设文件名仅支持字母、数字、下划线或短横线")
    return f"{base}.json"


def _persona_label(path: Path) -> str:
    """从人设文件读取展示标签。"""
    try:
        data = json.loads(_read_text(path))
    except json.JSONDecodeError:
        return path.stem
    return data.get("name") or path.stem


def _list_persona_configs() -> list[dict[str, str]]:
    """列出所有人设配置条目。"""
    if not PERSONA_DIR.exists():
        return []
    entries = []
    for path in sorted(PERSONA_DIR.glob("*.json")):
        label = _persona_label(path)
        entries.append({"id": f"persona:{path.name}", "label": f"人设：{label}"})
    return entries


def _resolve_config(config_id: str) -> Dict[str, Path | str] | None:
    """根据配置 ID 解析对应文件路径。"""
    if config_id in BASE_CONFIGS:
        return BASE_CONFIGS[config_id]
    if config_id.startswith("persona:"):
        filename = config_id.split(":", 1)[1]
        try:
            safe_name = _normalize_persona_filename(filename)
        except ValueError:
            return None
        path = (PERSONA_DIR / safe_name).resolve()
        try:
            path.relative_to(PERSONA_DIR.resolve())
        except ValueError:
            return None
        if not path.exists():
            return None
        return {"label": f"人设：{_persona_label(path)}", "path": path}
    return None


class WebHandler(BaseHTTPRequestHandler):
    """Web UI 的请求处理器。"""

    server_version = "AlicizationWeb/0.1"

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        """发送 JSON 响应。"""
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_api_error(self, status: int, message: str) -> None:
        """发送 API 错误响应。"""
        self._send_json(status, {"ok": False, "error": message})

    def _send_static(self, filename: str, content_type: str) -> None:
        """发送静态资源文件。"""
        path = STATIC_DIR / filename
        if not path.exists():
            self.send_error(404, "Not Found")
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        """读取并解析 JSON 请求体。"""
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 格式错误: {exc}") from exc

    def do_GET(self) -> None:
        """处理 GET 请求。"""
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_static("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_static("app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._send_static("styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/configs":
            configs = [
                {"id": key, "label": value["label"]}
                for key, value in BASE_CONFIGS.items()
            ]
            configs.extend(_list_persona_configs())
            self._send_json(200, {"configs": configs})
            return
        if parsed.path == "/api/config":
            params = parse_qs(parsed.query)
            config_id = (params.get("id") or [None])[0]
            if not config_id:
                self._send_api_error(404, "未知配置")
                return
            config = _resolve_config(config_id)
            if not config:
                self._send_api_error(404, "未知配置")
                return
            content = _read_text(config["path"])
            self._send_json(
                200,
                {"id": config_id, "label": config["label"], "content": content},
            )
            return
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        """处理 POST 请求。"""
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            params = parse_qs(parsed.query)
            config_id = (params.get("id") or [None])[0]
            if not config_id:
                self._send_api_error(404, "未知配置")
                return
            config = _resolve_config(config_id)
            if not config:
                self._send_api_error(404, "未知配置")
                return
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_api_error(400, str(exc))
                return
            content = payload.get("content", "")
            if not content.strip():
                self._send_api_error(400, "配置内容为空")
                return
            try:
                _write_json_pretty(config["path"], content)
            except json.JSONDecodeError as exc:
                self._send_api_error(400, f"JSON 格式错误: {exc}")
                return
            self._send_json(200, {"ok": True})
            return
        if parsed.path == "/api/persona":
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_api_error(400, str(exc))
                return
            raw_filename = payload.get("filename", "")
            content = payload.get("content", "")
            try:
                filename = _normalize_persona_filename(raw_filename)
            except ValueError as exc:
                self._send_api_error(400, str(exc))
                return
            if not content.strip():
                self._send_api_error(400, "配置内容为空")
                return
            PERSONA_DIR.mkdir(parents=True, exist_ok=True)
            path = (PERSONA_DIR / filename).resolve()
            try:
                path.relative_to(PERSONA_DIR.resolve())
            except ValueError:
                self._send_api_error(400, "人设文件名不合法")
                return
            if path.exists():
                self._send_api_error(409, "人设已存在")
                return
            try:
                _write_json_pretty(path, content)
            except json.JSONDecodeError as exc:
                self._send_api_error(400, f"JSON 格式错误: {exc}")
                return
            self._send_json(
                200,
                {"ok": True, "id": f"persona:{filename}", "label": _persona_label(path)},
            )
            return
        if parsed.path == "/api/run":
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_api_error(400, str(exc))
                return
            raw_seconds = payload.get("run_seconds", 5)
            try:
                run_seconds = int(raw_seconds)
            except (TypeError, ValueError):
                run_seconds = 5
            if run_seconds < 1:
                run_seconds = 1
            if run_seconds > MAX_RUN_SECONDS:
                run_seconds = MAX_RUN_SECONDS

            start = time.monotonic()
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "main.py"),
                        "--run-seconds",
                        str(run_seconds),
                    ],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=run_seconds + 5,
                )
                duration = time.monotonic() - start
                stdout = result.stdout or ""
                stderr = result.stderr or ""
            except subprocess.TimeoutExpired as exc:
                duration = time.monotonic() - start
                stdout = exc.stdout or ""
                stderr = (exc.stderr or "") + "\n[Run timed out]"
                result = subprocess.CompletedProcess(exc.cmd, 124)

            if len(stdout) > MAX_OUTPUT_CHARS:
                stdout = stdout[:MAX_OUTPUT_CHARS] + "\n[output truncated]"
            if len(stderr) > MAX_OUTPUT_CHARS:
                stderr = stderr[:MAX_OUTPUT_CHARS] + "\n[output truncated]"

            self._send_json(
                200,
                {
                    "ok": True,
                    "returncode": result.returncode,
                    "duration": round(duration, 3),
                    "run_seconds": run_seconds,
                    "stdout": stdout,
                    "stderr": stderr,
                },
            )
            return
        self.send_error(404, "Not Found")

    def log_message(self, format: str, *args: Any) -> None:
        """禁用默认日志输出。"""
        return


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """启动本地 Web UI 服务。"""
    server = ThreadingHTTPServer((host, port), WebHandler)
    print(f"Serving on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run_server()
