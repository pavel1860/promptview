from typing import Any, List

from promptview.vectors.embeddings.text_embeddings import DenseEmbeddings
from promptview.vectors.vectorizers.base import (VectorizerBase,
                                                     VectorizerDenseBase,
                                                     VectorMetrics)
from pydantic import BaseModel, Field
import tiktoken



def trim_and_stringify(doc):
    if isinstance(doc, str):
        return doc[:43000]
    return str(doc)[:43000]


def varify_type(doc):
    if isinstance(doc, str):
        return doc
    return str(doc)


class Tokenizer:
    def __init__(self, model="cl100k_base", max_tokens=8191):
        self._enc = tiktoken.get_encoding(model)
        self.max_tokens = max_tokens

    def tokenize(self, text):
        return self._enc.encode(text)
    
    def count_tokens(self, text):
        return len(self.tokenize(text))
    
    def trim_text(self, text):
        tokens = self.tokenize(text)
        return self._enc.decode(tokens[:self.max_tokens])
    
    def trim_texts(self, texts):
        return [self.trim_text(text) for text in texts]
        
    def detokenize(self, tokens):
        return self._enc.decode(tokens)


class TextVectorizer(VectorizerDenseBase):
    name: str = "dense"
    size: int = 1536
    dense_embeddings: DenseEmbeddings = Field(default_factory=DenseEmbeddings)
    metric: VectorMetrics = VectorMetrics.COSINE
    tokenizer: tiktoken.core.Encoding = Field(default_factory=Tokenizer)
    
    async def embed_documents(self, documents: List[str]):
        documents = self.tokenizer.trim_texts([varify_type(d) for d in documents])
        return await self.dense_embeddings.embed_documents(documents)
    
    async def embed_query(self, query: str):
        query = self.tokenizer.trim_text(varify_type(query))
        return await self.dense_embeddings.embed_query(query)