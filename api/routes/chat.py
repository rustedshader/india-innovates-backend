"""Chat API route — conversational Q&A over the knowledge graph."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agents.chat import GraphChatAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Singleton agent — initialized on first request (heavy: loads LLM connection)
_agent: GraphChatAgent | None = None


def _get_agent() -> GraphChatAgent:
    global _agent
    if _agent is None:
        _agent = GraphChatAgent()
    return _agent


def close_agent():
    global _agent
    if _agent is not None:
        _agent.close()
        _agent = None


# --- Request / Response models ---

class ChatMessage(BaseModel):
    role: str = Field(description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    question: str = Field(description="The user's question")
    history: list[ChatMessage] = Field(default_factory=list, description="Conversation history")


class ChatResponse(BaseModel):
    answer: str
    cypher: str | None = None
    route: str = ""


# --- Endpoint ---

@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Ask a question about the knowledge graph."""
    agent = _get_agent()
    history = [{"role": m.role, "content": m.content} for m in req.history]
    result = agent.chat(req.question, history=history)
    return ChatResponse(
        answer=result["answer"],
        cypher=result.get("cypher"),
        route=result.get("route", ""),
    )
