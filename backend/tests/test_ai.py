"""AI 对话（Pi Agent）— 路由测试。

覆盖：
- 内部工具回调端点（context / extract-preview / validate-config / save-config）
- 内部端点鉴权（x-internal-token）
- /ai/chat 未启用时 503
- /ai/chat SSE 事件翻译（mock PiAgentService）
- 附件路径越权防护（_resolve_attachment_path）
"""

# pyright: reportCallIssue=false

import base64
import json
from pathlib import Path
from typing import AsyncIterator

import pytest
from fastapi import HTTPException
from httpx2 import AsyncClient

from src.config import settings
from src.routers.ai import _TEMP_ROOT, _resolve_attachment_path


@pytest.fixture(autouse=True)
def _enable_pi():
    """默认启用 pi（各测试可自行覆盖）。"""
    old = settings.pi_enabled
    settings.pi_enabled = True
    yield
    settings.pi_enabled = old


@pytest.fixture
def configs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """把配置存储目录劫持到 tmp_path。"""
    d = tmp_path / "configs"
    d.mkdir()
    monkeypatch.setattr(
        "src.utils.daily_report_config._PROJECT_CONFIGS_DIR",
        d,
    )
    return d


def _minimal_config_dict() -> dict:
    """最小合法配置（labor 单块）。"""
    return {
        "schema_version": "2.0",
        "blocks": [
            {
                "category": "labor",
                "row_locator": {
                    "column": 0,
                    "label_regex": "^(?:现场人员|人员数量)$",
                },
                "rows": [
                    {"label_regex": "现场人员", "content_regex": "(.+)"},
                    {"label_regex": "人员数量", "content_regex": r"(\d+)"},
                ],
                "fields": {
                    "name": {"parts": [{"row": 0, "group": 0}]},
                    "quantity": {"parts": [{"row": 1, "group": 1}]},
                },
                "description": "AI 生成的 labor 解析块",
            }
        ],
    }


def _write_attachment(tmp_path: Path, content: bytes, name: str = "report.csv") -> str:
    """在受控临时目录下写入附件，返回路径。"""
    d = _TEMP_ROOT / "test-session"
    d.mkdir(parents=True, exist_ok=True)
    path = d / name
    path.write_bytes(content)
    return str(path)


# ============================================================================
# 内部端点鉴权
# ============================================================================


class TestInternalAuth:
    async def test_context_without_token_when_configured(self, client: AsyncClient):
        """配置了 token 时，缺 token 请求 403。"""
        old = settings.pi_internal_token
        settings.pi_internal_token = "secret-token"
        try:
            resp = await client.get("/internal/ai/projects/1/context")
            assert resp.status_code == 403
        finally:
            settings.pi_internal_token = old

    async def test_context_with_wrong_token(self, client: AsyncClient):
        old = settings.pi_internal_token
        settings.pi_internal_token = "secret-token"
        try:
            resp = await client.get(
                "/internal/ai/projects/1/context",
                headers={"x-internal-token": "wrong"},
            )
            assert resp.status_code == 403
        finally:
            settings.pi_internal_token = old

    async def test_context_with_correct_token(self, client: AsyncClient):
        old = settings.pi_internal_token
        settings.pi_internal_token = "secret-token"
        try:
            resp = await client.get(
                "/internal/ai/projects/1/context",
                headers={"x-internal-token": "secret-token"},
            )
            assert resp.status_code == 200
        finally:
            settings.pi_internal_token = old


# ============================================================================
# 内部端点：项目上下文
# ============================================================================


class TestInternalContext:
    async def test_context_shape(self, client: AsyncClient):
        resp = await client.get("/internal/ai/projects/1/context")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == 1
        assert "resources" in data
        assert "categories" in data
        assert "tag_dimensions" in data
        assert isinstance(data["resources"], list)
        assert isinstance(data["categories"], list)


# ============================================================================
# 内部端点：提取预览
# ============================================================================


class TestInternalExtractPreview:
    async def test_extract_preview_csv(self, client: AsyncClient, tmp_path: Path):
        csv_content = "col0,col1\n现场人员,张三\n人员数量,5人\n".encode("utf-8")
        path = _write_attachment(tmp_path, csv_content, "report.csv")
        resp = await client.post(
            "/internal/ai/projects/1/extract-preview",
            json={"file_path": path},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "report.csv"
        assert "日报文件预览" in data["markdownText"]

    async def test_extract_preview_missing_path(self, client: AsyncClient):
        resp = await client.post(
            "/internal/ai/projects/1/extract-preview",
            json={"file_path": "/etc/passwd"},
        )
        assert resp.status_code == 403

    async def test_extract_preview_bad_path_type(self, client: AsyncClient):
        resp = await client.post(
            "/internal/ai/projects/1/extract-preview",
            json={"file_path": 123},
        )
        assert resp.status_code == 400


# ============================================================================
# 内部端点：校验配置
# ============================================================================


class TestInternalValidate:
    async def test_validate_valid(self, client: AsyncClient):
        resp = await client.post(
            "/internal/ai/projects/1/validate-config",
            json={"config_json": _minimal_config_dict()},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["errors"] == []

    async def test_validate_invalid(self, client: AsyncClient):
        d = _minimal_config_dict()
        del d["blocks"][0]["fields"]["name"]
        resp = await client.post(
            "/internal/ai/projects/1/validate-config",
            json={"config_json": d},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert len(data["errors"]) > 0

    async def test_validate_with_sample(self, client: AsyncClient, tmp_path: Path):
        csv_content = "col0,col1\n现场人员,张三\n人员数量,5人\n".encode("utf-8")
        path = _write_attachment(tmp_path, csv_content, "sample.csv")
        resp = await client.post(
            "/internal/ai/projects/1/validate-config",
            json={
                "config_json": _minimal_config_dict(),
                "sample_file_path": path,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["parsedPreview"] is not None
        assert "items" in data["parsedPreview"]

    async def test_validate_rejects_non_object_config(self, client: AsyncClient):
        resp = await client.post(
            "/internal/ai/projects/1/validate-config",
            json={"config_json": "not-a-dict"},
        )
        assert resp.status_code == 400


# ============================================================================
# 内部端点：保存配置
# ============================================================================


class TestInternalSave:
    async def test_save_success(self, client: AsyncClient, configs_dir: Path):
        resp = await client.post(
            "/internal/ai/projects/1/save-config",
            json={
                "config_json": _minimal_config_dict(),
                "name": "AI 测试配置",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["configId"]) == 12
        # 落盘确认
        assert (configs_dir / "1" / f"{data['configId']}.json").exists()

    async def test_save_rejects_invalid(self, client: AsyncClient, configs_dir: Path):
        d = _minimal_config_dict()
        del d["blocks"][0]["fields"]["name"]
        resp = await client.post(
            "/internal/ai/projects/1/save-config",
            json={"config_json": d},
        )
        assert resp.status_code == 400


# ============================================================================
# 路径越权防护
# ============================================================================


class TestResolvePath:
    def test_ok_inside_temp(self, tmp_path: Path):
        d = _TEMP_ROOT / "sess"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "a.csv"
        f.write_bytes(b"x")
        assert _resolve_attachment_path(str(f)) == str(f.resolve())

    def test_outside_temp_rejected(self, tmp_path: Path):
        f = tmp_path / "evil.csv"
        f.write_bytes(b"x")
        with pytest.raises(HTTPException) as excinfo:
            _resolve_attachment_path(str(f))
        assert excinfo.value.status_code == 403

    def test_none_rejected(self):
        with pytest.raises(HTTPException) as excinfo:
            _resolve_attachment_path(None)
        assert excinfo.value.status_code == 400

    def test_symlink_escape_rejected(self, tmp_path: Path):
        """符号链接指向临时目录外 → resolve 后仍在临时目录内才算通过。"""
        outside = tmp_path / "outside.csv"
        outside.write_bytes(b"x")
        d = _TEMP_ROOT / "sess2"
        d.mkdir(parents=True, exist_ok=True)
        link = d / "link.csv"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("当前平台不支持符号链接")
        with pytest.raises(HTTPException) as excinfo:
            _resolve_attachment_path(str(link))
        assert excinfo.value.status_code == 403


# ============================================================================
# /ai/chat（未启用 / mock）
# ============================================================================


class TestAiChat:
    async def test_disabled_returns_503(self, client: AsyncClient):
        settings.pi_enabled = False
        resp = await client.post("/ai/chat", json={"message": "hi"})
        assert resp.status_code == 503
        assert "未启用" in resp.json()["detail"]

    async def test_chat_streams_events(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """mock PiAgentService.chat，验证 SSE 事件翻译。"""

        class FakeService:
            async def chat(
                self,
                session_id: str,
                message: str,
                attachment_hint: str = "",
            ) -> AsyncIterator[dict]:
                # 模拟 pi 事件序列
                yield {
                    "type": "message_update",
                    "assistantMessageEvent": {
                        "type": "text_delta",
                        "contentIndex": 0,
                        "delta": "正在",
                    },
                }
                yield {
                    "type": "message_update",
                    "assistantMessageEvent": {
                        "type": "text_delta",
                        "contentIndex": 0,
                        "delta": "分析…",
                    },
                }
                yield {
                    "type": "tool_execution_start",
                    "toolCallId": "call-1",
                    "toolName": "get_project_context",
                    "args": {"project_id": 1},
                }
                yield {
                    "type": "tool_execution_end",
                    "toolCallId": "call-1",
                    "toolName": "get_project_context",
                    "result": {
                        "content": [{"type": "text", "text": '{"resources": []}'}]
                    },
                    "isError": False,
                }
                yield {
                    "type": "message_end",
                    "message": {"content": [{"type": "text", "text": "分析完成"}]},
                }
                yield {"type": "agent_settled"}

        monkeypatch.setattr(
            "src.routers.ai.get_pi_agent_service",
            lambda: FakeService(),
        )

        resp = await client.post("/ai/chat", json={"message": "生成配置"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        body = resp.text
        assert "event: start" in body
        assert '"session_id"' in body
        # 增量文本
        assert "event: message_delta" in body
        assert "正在" in body
        assert "分析…" in body
        # 工具调用
        assert "event: tool_call" in body
        assert "get_project_context" in body
        assert "event: tool_result" in body
        # 最终文本
        assert "event: message_text" in body
        assert "分析完成" in body
        # 收尾
        assert "event: done" in body

    async def test_chat_with_attachment(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """带附件时，start 事件携带 attachment_paths，且文件落盘到会话目录。"""

        class FakeService:
            async def chat(self, *a, **kw) -> AsyncIterator[dict]:
                yield {"type": "agent_settled"}

        monkeypatch.setattr(
            "src.routers.ai.get_pi_agent_service",
            lambda: FakeService(),
        )

        csv_b64 = base64.b64encode(
            "col0,col1\n现场人员,张三\n".encode("utf-8")
        ).decode()
        resp = await client.post(
            "/ai/chat",
            json={
                "message": "分析日报",
                "attachments": [{"file_name": "日报.csv", "content_base64": csv_b64}],
            },
        )
        assert resp.status_code == 200
        body = resp.text
        assert "event: start" in body
        # 附件路径出现在 start 事件
        assert "attachment_paths" in body
        assert "日报.csv" in body
        # 附件文件确实落盘（路径来自 start 事件解析）
        start_line = next(line for line in body.split("\n") if line.startswith("data:"))
        payload = json.loads(start_line[5:])
        paths = payload.get("attachment_paths") or []
        assert paths, "attachment_paths 不应为空"
        assert Path(paths[0]).is_file()

    async def test_chat_invalid_base64(self, client: AsyncClient):
        resp = await client.post(
            "/ai/chat",
            json={
                "message": "x",
                "attachments": [
                    {"file_name": "a.csv", "content_base64": "!!!not-base64!!!"}
                ],
            },
        )
        assert resp.status_code == 400
        assert "base64" in resp.json()["detail"]
