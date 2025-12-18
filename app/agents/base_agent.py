from typing import Dict, Any, Optional
from app.utils.openai_client import openai_client


class BaseAgent:
    def __init__(self, name: str):
        self.name = name
        self.client = openai_client
        self.model = "gpt-4-turbo-preview"

    def call_llm(
        self,
        messages: list,
        temperature: float = 0.1,
        **kwargs
    ) -> Any:
        """Call OpenAI LLM"""
        if not self.client:
            raise Exception("OpenAI client not initialized. Check API key.")

        return self.client.chat_completion(
            messages=messages,
            model=self.model,
            temperature=temperature,
            **kwargs
        )

    def log(self, message: str):
        """Log a message"""
        print(f"[{self.name}] {message}")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name})>"
