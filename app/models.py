from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class ChatMessage:
    role: str
    content: str
    created_at: str
    generated: bool = False
    audio_path: Optional[str] = None
    display_content: Optional[str] = None
    auto_answer_source_kind: Optional[str] = None
    auto_answer_source_key: Optional[str] = None

    @classmethod
    def now(
        cls,
        role: str,
        content: str,
        audio_path: Optional[str] = None,
        generated: bool = False,
        display_content: Optional[str] = None,
        auto_answer_source_kind: Optional[str] = None,
        auto_answer_source_key: Optional[str] = None,
    ) -> "ChatMessage":
        return cls(
            role=role,
            content=content,
            created_at=datetime.now().isoformat(timespec="seconds"),
            generated=generated,
            audio_path=audio_path,
            display_content=display_content,
            auto_answer_source_kind=auto_answer_source_kind,
            auto_answer_source_key=auto_answer_source_key,
        )


@dataclass
class ChatSession:
    session_id: str
    title: str
    created_at: str
    updated_at: str
    model_name: str = ""
    messages: List[ChatMessage] = field(default_factory=list)
    reapply_short_instruction_after_rollover: bool = False

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "model_name": self.model_name,
            "messages": [m.__dict__ for m in self.messages],
            "reapply_short_instruction_after_rollover": self.reapply_short_instruction_after_rollover,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChatSession":
        session = cls(
            session_id=data["session_id"],
            title=data.get("title", "Neue Unterhaltung"),
            created_at=data.get("created_at", datetime.now().isoformat(timespec="seconds")),
            updated_at=data.get("updated_at", datetime.now().isoformat(timespec="seconds")),
            model_name=data.get("model_name", ""),
            reapply_short_instruction_after_rollover=bool(data.get("reapply_short_instruction_after_rollover", False)),
        )
        session.messages = [ChatMessage(**item) for item in data.get("messages", [])]
        return session