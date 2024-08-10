from typing import Any, List, Union
from botocore.vendored.six import itertools
import pinecone
from pinecone import Pinecone
import asyncio

from pydantic import BaseModel
# from pydantic.networks import Type
from components.text.text_client import TextClient
from components.vectors.embeddings.text_embeddings import Embeddings
from config import PINECONE_KEY, PINECONE_ENV
# from langchain.schema.embeddings import Embeddings
import langchain.schema.embeddings as lang_embeddings
from uuid import uuid4
import numpy as np


# pinecone.init(
#     api_key= PINECONE_KEY,
#     environment=PINECONE_ENV
# )


def chunks(iterable, batch_size=100):
    """A helper function to break an iterable into chunks of size batch_size."""
    it = iter(iterable)
    chunk = tuple(itertools.islice(it, batch_size))
    while chunk:
        yield chunk
        chunk = tuple(itertools.islice(it, batch_size))


class PineconeTextVectorStore:

    index: pinecone.Index
    namespace: Union[str, None] 


    def __init__(
            self, 
            index_name: str, 
            namespace: str, 
            embeddings: lang_embeddings.Embeddings=None, 
            metadata_model: BaseModel=None
            # metadata_model: Type[BaseModel]=None
        ) -> None:
        self.embeddings = TextClient() if not embeddings else embeddings
        self.pc = Pinecone(api_key=PINECONE_KEY)
        self.index = self.pc.Index(index_name)
        self.namespace = namespace
        self.metadata_model = metadata_model


    def validate_metadata_model(self, metadata):
        if self.metadata_model:
            if type(metadata) == dict:
                dict_metadata = self.metadata_model(**metadata).dict()
            elif type(metadata) == self.metadata_model:
                dict_metadata = metadata.dict()        
        else:
            if type(metadata) == dict:
                dict_metadata = metadata
            else:
                dict_metadata = metadata.dict()
        return {k: v for k, v in dict_metadata.items() if v is not None}
        

    def validate_list_metadata_model(self, metadata_list):
        if self.metadata_model:
            return [self.validate_metadata_model(metadata) for metadata in metadata_list]
        else:
            return metadata_list

    def add_text(self, text_id: str, text: str, metadata, namespace=None, embeddings: np.ndarray=None):
        metadata = self.validate_metadata_model(metadata)
        if embeddings is None:
            embeddings = self.embeddings.embed_documents(text)
        sparse_embeddings = embeddings['sparse_embeddings'][0]
        dense_embeddings = embeddings['dense_embeddings'][0]
        namespace = namespace or self.namespace
        # if image_id is None:
        # text_id = str(uuid4())
        # vector = (text_id, image_embeddings.tolist()[0], metadata)
        vector = {
            'id': text_id,
            'values': dense_embeddings,
            'metadata': metadata,
            'sparse_values': sparse_embeddings,
        }
        res = self.index.upsert(vectors=[vector], namespace=namespace)
        res['id'] = text_id
        res['embeddings'] = embeddings.tolist()[0]
        return res
    

    async def aadd_text(self, text_id: str, text: str, metadata, namespace=None, embeddings: np.ndarray=None):
        metadata = self.validate_metadata_model(metadata)
        if embeddings is None:
            embeddings = await self.embeddings.aembed_documents(text)
        sparse_embeddings = embeddings.sparse[0]
        dense_embeddings = embeddings.dense[0]
        namespace = namespace or self.namespace
        # if image_id is None:
        # text_id = str(uuid4())
        vector = {
            'id': text_id,
            'values': dense_embeddings,
            'metadata': metadata,
            'sparse_values': sparse_embeddings,
        }
        # res = self.index.upsert_async(vectors=[vector], namespace=namespace)
        res = await asyncio.to_thread(self.index.upsert, vectors=[vector], namespace=namespace)
        res['id'] = text_id
        # res['embeddings'] = embeddings
        return res

    def _pack_vectors(self, embeddings: List[Embeddings], metadata):
        # sparse_embeddings = embeddings.get('sparse_embeddings', None)
        # dense_embeddings = embeddings['dense_embeddings']
        sparse_embeddings = [e.sparse for e in embeddings]
        dense_embeddings = [e.dense for e in embeddings]

        if sparse_embeddings[0] is not None:
            return [{
                'id': str(uuid4()),
                'values': dense_emb,
                'metadata': metadata,
                'sparse_values': sparse_emb,
            } for dense_emb, sparse_emb, metadata in zip(dense_embeddings, sparse_embeddings, metadata)]
        else:
            return [{
                'id': str(uuid4()),
                'values': dense_emb,
                'metadata': metadata,
            } for dense_emb, metadata in zip(dense_embeddings, metadata)]

    
    async def aadd_documents(self, texts: List[str], metadata: List[dict], namespace=None, embeddings: np.ndarray=None, batch_size=100):
        metadata = self.validate_list_metadata_model(metadata)
        if embeddings is None:
            embeddings = await self.embeddings.aembed_documents(texts)        

        # sparse_embeddings = embeddings['sparse_embeddings']
        # dense_embeddings = embeddings['dense_embeddings']
        # ids = [str(uuid4()) for i in range(len(texts))]
        # vectors = zip(ids, dense_embeddings, sparse_embeddings, metadata)
        # vectors = [{
        #     'id': str(uuid4()),
        #     'values': dense_emb,
        #     'metadata': metadata,
        #     'sparse_values': sparse_emb,
        # } for dense_emb, sparse_emb, metadata in zip(dense_embeddings, sparse_embeddings, metadata)]
        vectors = self._pack_vectors(embeddings, metadata)
        namespace = namespace or self.namespace
        upserted_count = 0
        upserted_records = []
        for ids_vectors_chunk in chunks(vectors, batch_size=batch_size):
            res = await asyncio.to_thread(self.index.upsert, vectors=ids_vectors_chunk, namespace=namespace)
            upserted_count += res['upserted_count']
            upserted_records.extend(ids_vectors_chunk)
        return {
            'upserted_count': upserted_count,
            'records': upserted_records
        }
    

    def get_text_embeddings(self, text: str, namespace=None):
        namespace = namespace or self.namespace        
        text_embeddings = self.embeddings.embeddings(text)
        return text_embeddings
    
    

    # async def aget_image_embeddings(self, text: str, namespace=None):
    #     namespace = namespace or self.namespace        
    #     text_embeddings = await self.embeddings.aembeddings(text)
    #     return text_embeddings
    
    
    async def aget_similar_text(self, text_embedding: Embeddings, top_k: int=1, duplicate_threshold: float=0.99, namespace: str=None):
        namespace = namespace or self.namespace
        similar_texts = self.embedding_similarity_search(text_embedding, top_k=top_k, namespace=namespace)
        if len(similar_texts) > 0 and similar_texts[0].score > duplicate_threshold:
            return similar_texts[0]
        return None


    @property
    def dimension(self):
        return self.index.describe_index_stats()['dimension']
    

    @property
    def total_vector_count(self):
        return self.index.describe_index_stats()['total_vector_count']    

    @property
    def namespaces(self):
        return self.index.describe_index_stats()['namespaces']
        
    @property
    def index_fullness(self):
        return self.index.describe_index_stats()['index_fullness']



    def embedding_similarity_search(self, vector: np.ndarray, filter=None, top_k=10, namespace=None, include_metadata=True):
        namespace = namespace or self.namespace
        return self.index.query(
            vector=vector.tolist()[0],
            filter=filter,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata
        ).matches
    
    def query(self, text: str, filter=None, top_k=10, alpha=-1, namespace=None, include_metadata=True, embeddings: np.ndarray=None):
        return self.text_similarity_search(text, filter=filter, top_k=top_k, alpha=alpha, namespace=namespace, include_metadata=include_metadata, embeddings=embeddings)

    def text_similarity_search(self, text: str, filter=None, top_k=10, alpha=-1, namespace=None, include_metadata=True, embeddings: np.ndarray=None):
        namespace = namespace or self.namespace
        if embeddings is None:
            embeddings = self.embeddings.embed_query(text)
        # dense_embeddings = embeddings['dense_embeddings']
        # sparse_embeddings = embeddings['sparse_embeddings']
        if alpha != -1:
            embeddings = embeddings.avg(alpha)
            # if alpha < 0 or alpha > 1:
            #     raise Exception('alpha must be between 0 and 1')
            # dense_embeddings = [v * alpha for v in embeddings.dense]
            # sparse_embeddings = {
            #     'indices': embeddings.sparse['indices'],
            #     'values': [v * (1- alpha) for v in embeddings.sparse['values']]
            # }
        res = self.index.query(
            # vector=dense_embeddings,
            # sparse_vector=sparse_embeddings if alpha != -1 else None,
            vector=embeddings.dense,
            sparse_vector=embeddings.sparse if alpha != -1 else None,
            filter=filter,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata
        )
        return res.matches
    
    async def aquery(self, text: str, filter=None, top_k=10, alpha=-1, namespace=None, include_metadata=True, embeddings: np.ndarray=None):
        return await self.atext_similarity_search(text, filter=filter, top_k=top_k, alpha=alpha, namespace=namespace, include_metadata=include_metadata, embeddings=embeddings)
    

    async def atext_similarity_search(self, text: str, filter=None, top_k=10, alpha=-1, namespace=None, include_metadata=True, embeddings: np.ndarray=None):
        return await asyncio.to_thread(
            self.text_similarity_search,
            text=text, 
            filter=filter, 
            top_k=top_k, 
            alpha=alpha, 
            namespace=namespace, 
            include_metadata=include_metadata, 
            embeddings=embeddings
        )
        # namespace = namespace or self.namespace
        # if embeddings is None:
        #     embeddings = await self.embeddings.aembed_query(text)
        # # dense_embeddings = embeddings['dense_embeddings']
        # # sparse_embeddings = embeddings['sparse_embeddings']
        # if alpha != -1:
        #     if alpha < 0 or alpha > 1:
        #         raise Exception('alpha must be between 0 and 1')
        #     dense_embeddings = [v * alpha for v in embeddings['dense_embeddings']]
        #     sparse_embeddings = {
        #         'indices': embeddings['sparse_embeddings']['indices'],
        #         'values': [v * (1- alpha) for v in embeddings['sparse_embeddings']['values']]
        #     }
        # res = await asyncio.to_thread(self.index.query,
        #     vector=dense_embeddings,
        #     sparse_vector=sparse_embeddings if alpha != -1 else None,
        #     filter=filter,
        #     top_k=top_k,
        #     namespace=namespace,
        #     include_metadata=include_metadata
        # )
        # return res.matches
    
    async def get(self, record_id, namespace=None, include_metadata=True):
        namespace = namespace or self.namespace
        res = await asyncio.to_thread(
            self.index.query,
            id=record_id,
            top_k=1,
            namespace=namespace,
            include_metadata=include_metadata
        )
        if not res.matches:
            return None
        return res.matches[0]


    def get_many(self, top_k=100, namespace=None, include_metadata=True):
        namespace = namespace or self.namespace
        vector = [0 for i in range(self.dimension)]
        records = self.index.query(
            # vector=vector.tolist()[0],
            vector=vector,
            filter=None,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata
        )
        return records.matches
    
    async def aget_many(self, top_k=100, namespace=None, include_metadata=True):
        namespace = namespace or self.namespace
        vector = [0 for i in range(self.dimension)]
        records = await asyncio.to_thread(self.index.query,
            vector=vector,
            filter=None,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata
        )
        return records.matches
    
    def update(self, id: str, metadata: Any, namespace=None):
        namespace = namespace or self.namespace
        update_res = self.index.update(id, set_metadata=metadata, namespace=namespace )
        return update_res

    def delete(self, ids: Union[str, List[str]]=None, filter=None, delete_all=None, namespace=None):
        namespace = namespace or self.namespace
        if type(ids) == str:
            ids = [ids]
        return self.index.delete(
            ids, 
            filter=filter,
            delete_all=delete_all,
            namespace=namespace
        )
    
    async def adelete(self, ids: Union[str, List[str]]=None, filter=None, delete_all=None, namespace=None):
        namespace = namespace or self.namespace
        if type(ids) == str:
            ids = [ids]

        return await asyncio.to_thread(self.index.delete,
            ids, 
            filter=filter,
            delete_all=delete_all,
            namespace=namespace
        )
        

    @staticmethod
    def create_index(index_name, dimension, metric="dotproduct", pod_type="s1"):
        pinecone.create_index(
            index_name,
            dimension=dimension,
            metric=metric,
            pod_type=pod_type
        )

    @staticmethod
    def delete_index(index_name):
        pinecone.delete_index(index_name)