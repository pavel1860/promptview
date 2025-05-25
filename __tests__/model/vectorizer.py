from promptview.algebra.vectors.base_vectorizer import BaseVectorizer, VectorType
from typing import ClassVar, List
import numpy as np

class TestVectorizer(BaseVectorizer[str, np.ndarray]):
    model: str = "test"
    type: VectorType = "dense"
    dimension: ClassVar[int] = 4
    
    async def embed_documents(self, docs: list[str]) -> List[np.ndarray]:
        return [np.random.rand(self.dimension) for _ in range(len(docs))]
    
    async def embed_query(self, query: str) -> np.ndarray:
        return np.random.rand(self.dimension)
