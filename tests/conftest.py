"""pytest 全局注入：LLM_MODE=mock（仓规 mock-friendly——无 Key 无网全绿）。

v2 起 create_app 装配 LLM client（create_client env fail-fast，禁兜底），全量
测试经此注入统一走 MockLLMClient 零网络。conftest 在任何测试模块 import 之前
执行（webserver import 即 create_app），故在模块顶层强制注入；**强制覆盖而非
setdefault**——外泄的 LLM_MODE=live 会真网，测试面禁真网。测试内需要特殊 env
的（test_llm_bridge 等）自用 monkeypatch 管理，不受此基线影响。
"""

import os

os.environ["LLM_MODE"] = "mock"
