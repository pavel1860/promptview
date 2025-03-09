


import asyncio
from functools import singledispatchmethod
from typing import TypeVar, Generic
from pydantic import BaseModel, Field




T = TypeVar('T')
V = TypeVar('V')

class BaseVectorizer(BaseModel, Generic[V, T]):    
    
    
    class Config:
        arbitrary_types_allowed = True
    
    async def transform(self, doc: list[T]) -> list[V]:
        raise NotImplementedError("Unsupported type")



class BaseVector(BaseModel, Generic[V, T]):
    vector: V
    vectorizer: BaseVectorizer[V, T]
    size: int
    
    async def __call__(self, doc: T | list[T]):
        return await self.embed(doc)
    
    async def embed(self, doc: T | list[T]):
        if not isinstance(doc, list):
            doc = [doc]
        return await self.vectorizer.transform(doc)
    
    

import numpy as np
from promptview.vectors.embeddings.text_embeddings import DenseEmbeddings

openai_embeddings = DenseEmbeddings()

class OpenAIVectorizer(BaseVectorizer[list[float], str]):
    
    async def transform(self, doc: list[str]) -> list[list[float]]:
        return await openai_embeddings.embed_documents(doc)


class OpenAiVector(BaseVector):
    size: int = 1536
    vectorizer: OpenAIVectorizer = Field(default_factory=OpenAIVectorizer)
        
    





