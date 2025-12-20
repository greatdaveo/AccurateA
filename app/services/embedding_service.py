from typing import List, Dict, Any
from app.utils.openai_client import openai_client
import numpy as np

class EmbeddingService:
    """This converts text into vecto embeddings using OpenAI"""

    def __init__(self):
        self.client = openai_client
        self.model = "text-embedding-3-small"
        self.dimension = 1536

    def create_embedding(self, text: str) -> List[float]:
        """Create embedding for single text"""

        if not self.client:
            raise Exception("OpenAI client not initialised")

        text = text.strip().replace("\n", " ")

        response = self.client.client.embeddings.create(
            input=[text],
            model=self.model
        )

        return response.data[0].embedding

    def create_embeddings_batch(
        self,
        texts: List[str]
    ) -> List[List[float]]:
        """Create embeddings for multiple texts"""

        if not self.client:
            raise Exception("OpenAI client not initialized")

        cleaned_texts = [text.strip().replace("\n", " ") for t in texts]

        response = self.client.embeddings.create(
            input=cleaned_texts,
            model=self.model
        )

        return [item.embedding for item in response.data]

    def create_transaction_embedding(
        self,
        vendor: str,
        description: str = "",
        amount: float = 0.0
    ) -> List[float]:
        """Create embedding for transaction
            Combines vendor, description, and amount into one embedding.
        """
        text_parts = [f"Vendor: {vendor}"]

        if description:
            text_parts.append(f"Description: {description}")

        if amount > 0:
            rounded_amount = round(amount, 0)
            text_parts.append(f"Amount: ${rounded_amount}")

        text = " | ".join(text_parts)

        return self.create_embedding(text)


    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors (between -1 and 1)"""
        vec1_np = np.array(vec1)
        vec2_np = np.array(vec2)

        dot_product = np.dot(vec1_np, vec2_np)
        norm_1 = np.linalg.norm(vec1_np)
        norm_2 = np.linalg.norm(vec2_np)

        return float(dot_product / (norm_1 * norm_2))


embedding_service = EmbeddingService()


if __name__ == "__main__":
    print("============ Testing Embedding Service ==============")

    # Create embeddings for similar transactions
    text1 = "AWS cloud hosting services"
    text2 = "Amazon Web Services EC2"
    text3 = "GitHub subscription"

    print(f"\n Creating embeddings...")
    emb1 = embedding_service.create_embedding(text1)
    emb2 = embedding_service.create_embedding(text2)
    emb3 = embedding_service.create_embedding(text3)

    print(f"Embedding size: {len(emb1)} dimensions")
    print(f"Sample values: {emb1[:5]}...")

    print(f"\n Testing similarity...")
    sim_aws = embedding_service.cosine_similarity(emb1, emb2)
    sim_different = embedding_service.cosine_similarity(emb1, emb3)

    print(f"'AWS' vs 'Amazon Web Services': {sim_aws:.4f} - higher")
    print(f"'AWS' vs 'GitHub': {sim_different:.4f} - lower")

    print("\n ======= Embedding service working! ======")



