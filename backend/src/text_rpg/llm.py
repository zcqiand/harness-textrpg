"""LLM 桥接层（v2/v3 design spec §5.1 env 契约 + §4 裁定 0）。

三个部件：
- env fail-fast 工厂 :func:`create_client` —— ``LLM_MODE`` 必填（禁兜底，2026-08-28
  漂移事故纪律）；live 三键缺一即拒并点名缺哪个；mock 三键不读。
- :class:`MockLLMClient` —— 零网络、确定性回复表（关键词命中→固定回复，未命中→默认
  回复），驱动后续护栏/记忆断言。
- :class:`LiveLLMClient` —— httpx 裸调 OpenAI 兼容 ``/chat/completions``，重试 3 次
  指数退避（sleep 可注入），统一 :class:`LLMError`，剥 ``<think>`` 内联思维链（MiniMax
  指纹，母仓 text-adventure-rpg 同款正则）。
"""
# @impl M02.F05.I04

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable

import httpx

__all__ = [
    "LLMError",
    "LiveLLMClient",
    "MockLLMClient",
    "create_client",
    "strip_think",
]

_LIVE_KEYS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

_DEFAULT_REPLY = "……"

_ATTEMPTS = 3
_BACKOFF_BASE = 0.5


class LLMError(RuntimeError):
    """LLM 桥接层统一错误：env 配置失败 / 重试耗尽 / 响应形状不符。"""


def strip_think(text: str) -> str:
    """剥 ``<think>…</think>`` 内联思维链并去首尾空白。"""
    return _THINK_RE.sub("", text).strip()


class MockLLMClient:
    """零网络 mock 客户端：关键词回复表 + 默认回复，确定性。"""

    def __init__(
        self, default_reply: str = _DEFAULT_REPLY, reply_table: dict[str, str] | None = None
    ) -> None:
        self.default_reply = default_reply
        self.reply_table = reply_table or {}

    def generate(self, system_prompt: str, user_text: str) -> str:
        for keyword, reply in self.reply_table.items():
            if keyword in user_text:
                return reply
        return self.default_reply


class LiveLLMClient:
    """OpenAI 兼容 live 客户端：重试 + 退避 + 统一 LLMError + 剥 think。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._transport = transport
        self._timeout = timeout
        self._sleep = sleep

    def generate(self, system_prompt: str, user_text: str) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        last_reason = ""
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                resp = self._post(url, payload, headers)
                content = self._extract(resp)
            except (LLMError, httpx.TransportError) as exc:
                # TransportError（ConnectError/ReadTimeout 等）与形状/状态码失败同账：
                # 计入重试，耗尽统一 LLMError（spec §2「失败重试+统一错误形状」）。
                last_reason = str(exc)
                if attempt < _ATTEMPTS:
                    self._sleep(_BACKOFF_BASE * 2 ** (attempt - 1))
            else:
                return strip_think(content)
        raise LLMError(f"LLM 调用重试耗尽（{_ATTEMPTS} 次）：{last_reason}")

    def _post(self, url: str, payload: dict, headers: dict) -> httpx.Response:
        with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
            resp = client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        return resp

    @staticmethod
    def _extract(resp: httpx.Response) -> str:
        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"叙事后端响应形状不符: {resp.text[:200]!r}") from exc
        if not isinstance(content, str):
            raise LLMError(f"响应 content 不是字符串: {content!r}")
        return content


def create_client() -> tuple[MockLLMClient | LiveLLMClient, str]:
    """按 LLM_MODE 装配客户端，单源下发 (client, mode)（env fail-fast，禁兜底；
    mode 随返回值走，消费方不再二次直读 env）。"""
    mode = os.environ.get("LLM_MODE")
    if mode is None:
        raise LLMError("缺少环境变量 LLM_MODE")
    if mode == "mock":
        return MockLLMClient(), "mock"
    if mode == "live":
        missing = [k for k in _LIVE_KEYS if not os.environ.get(k)]
        if missing:
            raise LLMError(f"LLM_MODE=live 缺少环境变量：{', '.join(missing)}")
        return (
            LiveLLMClient(
                base_url=os.environ["LLM_BASE_URL"],
                api_key=os.environ["LLM_API_KEY"],
                model=os.environ["LLM_MODEL"],
            ),
            "live",
        )
    raise LLMError(f"LLM_MODE 非法值：{mode!r}（只认 mock/live）")
