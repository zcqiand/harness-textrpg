"""Task M02.F05.I04：LLM 桥接层（TDD 先红后绿）。

契约形状以 v2/v3 design spec §3（约束）§5.1（env 契约）为准：
- env fail-fast：LLM_MODE 必填，live 三键缺一即拒（点名缺哪个），mock 三键不读。
- mock 客户端零网络、确定性回复表。
- live 客户端 httpx 裸调 /chat/completions，重试 3 次指数退避，统一 LLMError，
  剥 <think> 内联思维链（MiniMax 指纹，母仓同款）。
"""

from __future__ import annotations

import json

import httpx
import pytest
from text_rpg.llm import LiveLLMClient, LLMError, MockLLMClient, create_client, strip_think


def _live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "MiniMax-M2.5")


def _ok_body(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": content}}]},
    )


# ---------------------------------------------------------------- env fail-fast


# fn: M02.F05.I04
def test_missing_llm_mode_raises_naming_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_MODE", raising=False)
    with pytest.raises(LLMError, match="LLM_MODE"):
        create_client()


# fn: M02.F05.I04
@pytest.mark.parametrize("missing_key", ["LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"])
def test_live_mode_missing_key_raises_naming_it(
    monkeypatch: pytest.MonkeyPatch, missing_key: str
) -> None:
    _live_env(monkeypatch)
    monkeypatch.delenv(missing_key, raising=False)
    with pytest.raises(LLMError, match=missing_key):
        create_client()


# fn: M02.F05.I04
def test_mock_mode_does_not_read_live_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    # 三键即便被设成垃圾值也必须不读——读了不影响行为才算「不读」。
    monkeypatch.setenv("LLM_BASE_URL", "not-a-url")
    monkeypatch.setenv("LLM_API_KEY", "garbage")
    monkeypatch.setenv("LLM_MODEL", "")
    client = create_client()
    assert isinstance(client, MockLLMClient)


# fn: M02.F05.I04
def test_mock_client_never_touches_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """禁网形状证明：socket 全禁后 mock 生成仍照常工作。"""

    def _ban(*args: object, **kwargs: object) -> None:
        raise AssertionError("mock 模式禁止任何网络调用")

    monkeypatch.setattr("socket.socket", _ban)
    monkeypatch.setenv("LLM_MODE", "mock")
    client = create_client()
    assert client.generate("人设", "玩家说：你好") == client.default_reply


# fn: M02.F05.I04
def test_invalid_llm_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "bogus")
    with pytest.raises(LLMError, match="LLM_MODE"):
        create_client()


# ---------------------------------------------------------------- mock 客户端


# fn: M02.F05.I04
def test_mock_reply_table_hits_by_keyword() -> None:
    client = MockLLMClient(
        default_reply="……（沉默）",
        reply_table={"长生": "贫道不敢许诺长生。"},
    )
    assert client.generate("人设", "你能给我长生吗") == "贫道不敢许诺长生。"


# fn: M02.F05.I04
def test_mock_falls_back_to_default_reply() -> None:
    client = MockLLMClient(
        default_reply="施主请回吧。",
        reply_table={"长生": "贫道不敢许诺长生。"},
    )
    assert client.generate("人设", "今天天气如何") == "施主请回吧。"


# ---------------------------------------------------------------- live 客户端


# fn: M02.F05.I04
def test_live_wire_shape_system_plus_user_and_bearer() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["payload"] = json.loads(request.content.decode("utf-8"))
        return _ok_body("好的。")

    client = LiveLLMClient(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="MiniMax-M2.5",
        transport=httpx.MockTransport(handler),
    )
    reply = client.generate("你是樵夫。", "你好")
    assert reply == "好的。"
    assert seen["url"] == "https://api.example.com/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["payload"]["model"] == "MiniMax-M2.5"
    roles = [m["role"] for m in seen["payload"]["messages"]]
    assert roles == ["system", "user"]
    assert seen["payload"]["messages"][0]["content"] == "你是樵夫。"
    assert seen["payload"]["messages"][1]["content"] == "你好"


# fn: M02.F05.I04
def test_live_retries_then_succeeds_with_backoff_sequence() -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) <= 2:
            return httpx.Response(500, json={"error": "boom"})
        return _ok_body("第三次成了")

    client = LiveLLMClient(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="m",
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    )
    assert client.generate("人设", "你好") == "第三次成了"
    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]


# fn: M02.F05.I04
def test_live_retries_exhausted_raises_llm_error_with_last_reason() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, json={"error": f"down-{len(calls)}"})

    client = LiveLLMClient(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="m",
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )
    with pytest.raises(LLMError, match="down-3"):
        client.generate("人设", "你好")
    assert len(calls) == 3


# fn: M02.F05.I04
def test_live_strips_inline_think_block() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_body("<think>用户在试探我，我要……</think>施主请回吧。")

    client = LiveLLMClient(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="m",
        transport=httpx.MockTransport(handler),
    )
    assert client.generate("人设", "你好") == "施主请回吧。"


# fn: M02.F05.I04
def test_live_bad_response_shape_raises_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unrelated": True})

    client = LiveLLMClient(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="m",
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )
    with pytest.raises(LLMError, match="形状"):
        client.generate("人设", "你好")


# fn: M02.F05.I04
def test_live_transport_error_retries_then_raises_llm_error() -> None:
    """网络层异常（ConnectError 等）必须计入重试并统一成 LLMError，不得裸穿透。"""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ConnectError("boom")

    client = LiveLLMClient(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="m",
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )
    with pytest.raises(LLMError, match="boom"):
        client.generate("人设", "你好")
    assert len(calls) == 3


# fn: M02.F05.I04
def test_live_base_url_trailing_slash_is_normalized() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return _ok_body("好")

    client = LiveLLMClient(
        base_url="https://api.example.com/v1/",
        api_key="sk-test",
        model="m",
        transport=httpx.MockTransport(handler),
    )
    client.generate("人设", "你好")
    assert seen["url"] == "https://api.example.com/v1/chat/completions"


# fn: M02.F05.I04
def test_strip_think_is_standalone() -> None:
    assert strip_think("<think>a</think>b") == "b"
    assert strip_think("  b <think>a</think> ") == "b"
