from typing import List, Dict, Any, Optional
from pinecone import Pinecone, ServerlessSpec
from app.config import settings
from app.services.embedding_service import embedding_service



class VectorStore:
    """This is where AI store its memory of past classifications"""
    def __init__(self):
        if not settings.pinecone_api_key:
            raise Exception("Pinecone API key not configured")

        self.pc = Pinecone(api_key=settings.pinecone_api_key)
        self.index_name = settings.pinecone_index_name

        # Get or create index
        self._ensure_index_exists()

        # Connect to index
        self.index = self.pc.Index(self.index_name)


    def _ensure_index_exists(self):
        """Ensure pinecone index exists or create it if it doesn't exit"""
        # List existing indexes
        existing_indexes = [idx.name for idx in self.pc.list_indexes()]

        if self.index_name not in existing_indexes:
            print(f"Creating Pinecone Index: {self.index_name}")

            # Create index
            self.pc.create_index(
                name=self.index_name,
                dimension=1536, #OpenAI embedding size
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region=settings.pinecone_environment or "us-east-1"
                )
            )

            print(f"====== Index Created: {self.index_name}")

    def store_classification_pattern(
        self,
        pattern_id: str,
        company_id: str,
        vendor: str,
        description: str,
        amount: float,
        category: str,
        account_code: str,
        account_id: str,
        confidence: float,
        source: str = "ai"  # ai, user
    ):
        """This is how the AI remembers by storing classification pattern"""
        # Create embedding
        embedding = embedding_service.create_transaction_embedding(
            vendor=vendor,
            description=description,
            amount=amount
        )

        #Prepare metadata
        metadata = {
            "company_id": company_id,
            "vendor": vendor,
            "description": description or "",
            "amount": float(amount),
            "category": category,
            "account_code": account_code,
            "account_id": account_id,
            "confidence": float(confidence),
            "source": source,  # Important: user corrections have higher priority
        }

        # Store in Pinecone
        self.index.upsert(
            vectors=[
                {
                    "id": pattern_id,
                    "values": embedding,
                    "metadata": metadata
                }
            ],
            namespace=company_id #Isolate by company
        )


    def find_similar_patterns(
        self,
        company_id: str,
        vendor: str,
        description: str = "",
        amount: float = 0.0,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """This is how AI learns from similar classification patterns by finding similar classification patterns"""

        # Create query embedding
        query_embedding = embedding_service.create_transaction_embedding(
            vendor=vendor,
            description=description,
            amount=amount
        )

        # Query Pinecone
        results = self.index.query(
            vector=query_embedding,
            top_k=top_k,
            namespace=company_id,
            include_metadata=True
        )

        #Format results
        patterns = []
        for match in results.matches:
            patterns.append({
                "id": match.id,
                "score": match.score, # Similarity score (0-1)
                "metadata": match.metadata
            })

        return patterns


    def get_patterns_stats(self, company_id: str) -> Dict[str, Any]:
        """Get statistics about stored patterns"""

        stats = self.index.describe_index_stats()

        # Get namespace stats
        namespace_stats = stats.namespaces.get(company_id, {})

        return {
            "total_patterns": namespace_stats.get("vector_count", 0),
            "index_fullness": stats.index_fullness
        }


    def delete_pattern(self, pattern_id: str, company_id: str):
        """Delete a pattern"""
        self.index.delete(
            ids=[pattern_id],
            namespace=company_id
        )


try:
    vector_store = VectorStore()
except Exception as e:
    print(f"Vector store initialization failed: {e}")
    print("Continuing without vector store")
    vector_store = None

if __name__ == "__main__":
    # Test vector store
    print("=========== Testing Vector Store ==============")

    if not vector_store:
        print("-------- Vector store not available")
        exit(1)

    # Test pattern storage
    print("\n Storing test pattern...")
    vector_store.store_classification_pattern(
        pattern_id="test-pattern-1",
        company_id="test-company",
        vendor="AWS",
        description="Cloud hosting services",
        amount=150.00,
        category="Cloud Infrastructure",
        account_code="6200",
        account_id="test-account-123",
        confidence=0.98,
        source="ai"
    )
    print("-------- Pattern stored")

    # Test similarity search
    print("\n ======== Searching for similar patterns...")
    similar = vector_store.find_similar_patterns(
        company_id="test-company",
        vendor="Amazon Web Services",
        description="EC2 hosting",
        amount=145.00
    )

    print(f" Found {len(similar)} similar patterns:")
    for pattern in similar:
        print(f" - Score: {pattern['score']:.4f}")
        print(f" Vendor: {pattern['metadata']['vendor']}")
        print(f" Category: {pattern['metadata']['category']}")

    # Get stats
    print("\n ========= Getting stats...")
    stats = vector_store.get_patterns_stats("test-company")
    print(f" Total patterns: {stats['total_patterns']}")

    # Cleanup
    print("\n Cleaning up test data...")
    vector_store.delete_pattern("test-pattern-1", "test-company")
    print(" Test data removed")

    print("\n Vector store working!")









