from typing import Any, List

from promptview.vectors.embeddings.text_embeddings import DenseEmbeddings
from promptview.vectors.vectorizers.base import (VectorizerBase,
                                                     VectorizerDenseBase,
                                                     VectorMetrics)
from pydantic import BaseModel, Field




def trim_and_stringify(doc):
    if isinstance(doc, str):
        return doc[:43000]
    return str(doc)[:43000]


class TextVectorizer(VectorizerDenseBase):
    name: str = "dense"
    size: int = 1536
    dense_embeddings: DenseEmbeddings = Field(default_factory=DenseEmbeddings)
    metric: VectorMetrics = VectorMetrics.COSINE
    
    async def embed_documents(self, documents: List[str]):
        documents = [trim_and_stringify(doc) for doc in documents]
        return await self.dense_embeddings.embed_documents(documents)
    
    async def embed_query(self, query: str):
        return await self.dense_embeddings.embed_query(query)