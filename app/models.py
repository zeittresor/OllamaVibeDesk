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
    def from_dict(cls, data: dict) -> "ChatMessage":
        raw = data if isinstance(data, dict) else {}
        role = str(raw.get("role", "user") or "user").strip().lower()
        if role not in {"user", "assistant"}:
            role = "user"
        return cls(
            role=role,
            content=str(raw.get("content", "") or ""),
            created_at=str(raw.get("created_at", datetime.now().isoformat(timespec="seconds")) or datetime.now().isoformat(timespec="seconds")),
            generated=bool(raw.get("generated", False)),
            audio_path=str(raw.get("audio_path")) if raw.get("audio_path") else None,
            display_content=str(raw.get("display_content")) if raw.get("display_content") is not None else None,
            auto_answer_source_kind=str(raw.get("auto_answer_source_kind")) if raw.get("auto_answer_source_kind") else None,
            auto_answer_source_key=str(raw.get("auto_answer_source_key")) if raw.get("auto_answer_source_key") else None,
        )

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
        raw = data if isinstance(data, dict) else {}
        session_id = str(raw.get("session_id", "") or "").strip()
        if not session_id:
            raise ValueError("Chat session is missing its session_id")
        session = cls(
            session_id=session_id,
            title=str(raw.get("title", "Neue Unterhaltung") or "Neue Unterhaltung"),
            created_at=str(raw.get("created_at", datetime.now().isoformat(timespec="seconds")) or datetime.now().isoformat(timespec="seconds")),
            updated_at=str(raw.get("updated_at", datetime.now().isoformat(timespec="seconds")) or datetime.now().isoformat(timespec="seconds")),
            model_name=str(raw.get("model_name", "") or ""),
            reapply_short_instruction_after_rollover=bool(raw.get("reapply_short_instruction_after_rollover", False)),
        )
        raw_messages = raw.get("messages", [])
        if not isinstance(raw_messages, list):
            raw_messages = []
        session.messages = [ChatMessage.from_dict(item) for item in raw_messages if isinstance(item, dict)]
        return session
