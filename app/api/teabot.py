from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User
from app.agents.teabot_agent import TeaBotAgent

router = APIRouter(
    prefix="/teabot",
    tags=["TeaBot AI Assistant"]
)

class ChatMessage(BaseModel):
    """Chat message"""
    role: str  # 'user' or 'assistant'
    content: str

class ChatRequest(BaseModel):
    """Chat request"""
    message: str
    conversation_history: Optional[List[ChatMessage]] = None

class ChatResponse(BaseModel):
    """Chat response"""
    message: str
    suggested_questions: List[str]


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat with TeaBot",
    description="Ask TeaBot about your finances, taxes, or business"
)
async def chat_with_teabot(
        chat_request: ChatRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Chat with TeaBot

    TeaBot is your AI financial advisor who can:
    - Explain your financial statements
    - Identify tax opportunities
    - Spot spending patterns
    - Give budgeting advice
    - Answer accounting questions
    """
    try:
        # Initialize TeaBot
        teabot = TeaBotAgent(db, str(current_user.company_id), user=current_user)

        # Convert conversation history to proper format
        history = None
        if chat_request.conversation_history:
            history = [
                {
                    'role': msg.role,
                    'content': msg.content
                }
                for msg in chat_request.conversation_history
            ]

        # Get response
        response = teabot.chat(
            user_message=chat_request.message,
            conversation_history=history
        )

        # Get suggested questions
        suggestions = teabot.get_suggested_questions()

        return ChatResponse(
            message=response,
            suggested_questions=suggestions
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TeaBot error: {str(e)}"
        )


@router.get(
    "/suggested-questions",
    summary="Get suggested questions",
    description="Get a list of questions users can ask TeaBot"
)
async def get_suggested_questions(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Get suggested questions for TeaBot"""
    teabot = TeaBotAgent(db, str(current_user.company_id), user=current_user)
    suggestions = teabot.get_suggested_questions()

    return {
        'questions': suggestions
    }


@router.get(
    "/financial-summary",
    summary="Get financial context",
    description="Get the financial data TeaBot uses for context"
)
async def get_financial_summary(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get Financial Summary

    Returns the same financial context TeaBot sees.
    Useful for debugging or showing users what data TeaBot has.
    """
    try:
        teabot = TeaBotAgent(db, str(current_user.company_id), user=current_user)
        context = teabot._get_financial_context()

        return {
            'success': True,
            'context': context
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )