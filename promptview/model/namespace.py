
from __future__ import annotations
from typing import Type

from qdrant_client import QdrantClient
from pydantic import BaseModel, Field
from promptview.model.fields import VectorSpaceMetrics
from promptview.model.vectors.base_vectorizer import BaseVectorizer





class VectorSpace:
    name: str
    vectorizer: Type[BaseVectorizer]
    metric: VectorSpaceMetrics
    
    def __init__(self, name: str, vectorizer: Type[BaseVectorizer], metric: VectorSpaceMetrics):
        self.name = name
        self.vectorizer = vectorizer
        self.metric = metric
    

    
class NamespaceParams:
    name: str
    vector_spaces: dict[str, VectorSpace]
    connection: QdrantClient
    
    def __init__(self, name: str, vector_spaces: dict[str, VectorSpace], connection: QdrantClient):
        self.name = name
        self.vector_spaces = vector_spaces
        self.connection = connection
    