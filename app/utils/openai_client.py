from openai import OpenAI
from app.config import settings

class OpenAIClient:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
        self.default_model = "gpt-4-turbo-preview"

    def chat_completion(
        self,
        messages: list,
        model: str = None,
        temperature: float = 0.1,
        **kwargs
    ):
        """Create a chat completion with OPEN AI"""
        return self.client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            temperature=temperature,
            **kwargs
        )


    def test_connection(self) -> bool:
        """Test if OPEN AI API is working"""
        try:
            response = self.chat_completion(
                messages=[
                    {"role": "user", "content": "Say 'OK' if you can hear me!"}
                ],
                max_tokens=10
            )
            return True
        except Exception as e:
            print(f"OpenAI Connection Failed {e}")
            return False

openai_client = OpenAIClient(api_key=settings.openai_api_key) if settings.openai_api_key else None


if __name__ == "__main__":
    print("=== Testing OpenAI Connection ======")

    if not openai_client:
        print("OpenAI API Key not configured")
    elif openai_client.test_connection():
        print("OpenAI connection successful!")
    else:
        print("OpenAI connection failed")

