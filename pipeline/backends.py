"""모델 호출 백엔드. 오케스트레이터는 complete()만 안다."""
from __future__ import annotations

import os
from typing import Protocol


class Backend(Protocol):
    def complete(self, role: str, system: str, user: str, web_search: bool = False) -> str: ...


class AnthropicBackend:
    """Anthropic API 백엔드. ANTHROPIC_API_KEY 환경변수가 필요하다.

    리서치·주제 선정 역할에는 서버 측 웹 검색 도구를 연결한다.
    """

    def __init__(self, model: str | None = None, max_tokens: int = 16000, max_searches: int = 8):
        import anthropic  # 지연 임포트: 테스트에서는 SDK 없이도 동작

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("SOCIALNEWS_MODEL", "claude-sonnet-5-5")
        self.max_tokens = max_tokens
        self.max_searches = max_searches

    def complete(self, role: str, system: str, user: str, web_search: bool = False) -> str:
        kwargs: dict = {}
        if web_search:
            kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": self.max_searches}]
        messages = [{"role": "user", "content": user}]
        text_parts: list[str] = []
        for _ in range(6):  # 서버 도구가 턴을 일시 중단(pause_turn)하면 이어서 진행
            resp = self.client.messages.create(
                model=self.model, max_tokens=self.max_tokens, system=system, messages=messages, **kwargs
            )
            text_parts += [b.text for b in resp.content if getattr(b, "type", "") == "text"]
            if resp.stop_reason != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": resp.content}]
        return "".join(text_parts)
