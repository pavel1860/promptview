import json
from typing import Any, Dict, List, Union
from botocore.vendored.six import itertools
import pinecone
from pinecone import Pinecone
import asyncio

from pydantic import BaseModel
# from pydantic.networks import Type
# from ...common.vectors.embeddings.text_embeddings import Embeddings
from ...vectors.embeddings.text_embeddings import Embeddings
# from config import PINECONE_KEY, PINECONE_ENV
# from langchain.schema.embeddings import Embeddings
import langchain.schema.embeddings as lang_embeddings
from uuid import uuid4
import numpy as np
import os

PINECONE_KEY = os.getenv('PINECONE_KEY')


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

class PineconeSearchResult:

    def __init__(self, id, score, metadata, dense_vec=None, sparse_vec=None):
        self.id = id
        self.score = score
        self.metadata = metadata
        self.embedding = Embeddings(dense=dense_vec, sparse=sparse_vec)


class PineconeVectorStore:

    index: pinecone.Index
    namespace: Union[str, None] 


    def __init__(
            self, 
            index_name: str, 
            namespace: str, 
            metadata_model: BaseModel=None
            # metadata_model: Type[BaseModel]=None
        ) -> None:
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
        return dict_metadata
        
        
    def serialize_metadata(self, metadata):
        if self.metadata_model:
            if type(metadata) == dict:
                dict_metadata = self.metadata_model(**metadata).dict()
            elif type(metadata) == self.metadata_model:
                if hasattr(metadata, "to_dict"):
                    dict_metadata = metadata.to_dict()
                else:
                    dict_metadata = metadata.dict()        
            else:
                raise Exception('restart Jupyter: metadata must be a dict or an instance of metadata_model.')
        else:
            if type(metadata) == dict:
                dict_metadata = metadata
            else:
                dict_metadata = metadata.dict()
        san_metadata = {}
        for k, v in dict_metadata.items():
            if v is None:
                continue
            if type(v) == list or type(v) == dict:
                san_metadata[k] = json.dumps(v)
            else:
                san_metadata[k] = v
        return san_metadata



    def serialize_list_metadata_model(self, metadata_list):
        if self.metadata_model:
            return [self.serialize_metadata(metadata) for metadata in metadata_list]
        else:
            return metadata_list


    def deserialize_metadata(self, metadata, parse_model=True):
        des_metadata = {}
        for k, v in metadata.items():
            if type(v) == str:
                try:
                    des_metadata[k] = json.loads(v)
                except:
                    des_metadata[k] = v
            else:
                des_metadata[k] = v

        if self.metadata_model and parse_model:
            return self.metadata_model(**des_metadata)
        else:
            return des_metadata


    def validate_list_metadata_model(self, metadata_list):
        if self.metadata_model:
            return [self.validate_metadata_model(metadata) for metadata in metadata_list]
        else:
            return metadata_list

    

    def _pack_vectors(self, embeddings: List[Embeddings], metadata, ids=None):
        sparse_embeddings = [e.sparse for e in embeddings]
        dense_embeddings = [e.dense for e in embeddings]
        if not ids:
            ids = [str(uuid4()) for i in range(len(embeddings))]

        if sparse_embeddings[0] is not None:
            return [{
                'id': i,
                'values': dense_emb,
                'metadata': metadata,
                'sparse_values': sparse_emb,
            } for i, dense_emb, sparse_emb, metadata in zip(ids, dense_embeddings, sparse_embeddings, metadata)]
        else:
            return [{
                'id': i,
                'values': dense_emb,
                'metadata': metadata,
            } for i, dense_emb, metadata in zip(ids, dense_embeddings, metadata)]

    
    async def add_documents(self, embeddings: Embeddings, metadata: List[Union[Dict, BaseModel]], ids=None, namespace=None, batch_size=100):
        namespace = namespace or self.namespace        
        metadata = self.serialize_list_metadata_model(metadata)
        vectors = self._pack_vectors(embeddings, metadata, ids)
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
    
    def embeddings_avg(self, emb, alpha):
        if alpha < 0 or alpha > 1:
            raise Exception('alpha must be between 0 and 1')
        dense_embeddings = [v * alpha for v in emb.dense]
        sparse_embeddings = {
            'indices': emb.sparse['indices'],
            'values': [v * (1- alpha) for v in emb.sparse['values']]
        } if emb.sparse else None
        return Embeddings(
            dense=dense_embeddings,
            sparse=sparse_embeddings
        )


    async def similarity(self, query: Embeddings, top_k=3, alpha=None, filter=None, namespace=None, include_metadata=True, parse_model=True, include_values=False):
        namespace = namespace or self.namespace        
        # results = await asyncio.to_thread(
        #     self.index.query,
        #     vector=query.dense,
        #     filter=filter,
        #     top_k=top_k,
        #     namespace=namespace,
        #     include_metadata=include_metadata,
        #     include_values=include_values
        # )
        if alpha is not None:
            results = await self._hybrid_similarity(
                query=query,
                top_k=top_k,
                alpha=alpha,
                filter=filter,
                namespace=namespace,
                include_metadata=include_metadata,
                parse_model=parse_model,
                include_values=include_values
            )
        else:
            results = await self._dense_similarity(
                query=query,
                top_k=top_k,
                filter=filter,
                namespace=namespace,
                include_metadata=include_metadata,
                parse_model=parse_model,
                include_values=include_values
            )
        return self._pack_result(results, parse_model=parse_model)
    
    
    async def _dense_similarity(self, query: Embeddings, top_k=3, filter=None, namespace=None, include_metadata=True, parse_model=True, include_values=False):        
        return await asyncio.to_thread(
            self.index.query,
            vector=query.dense,
            filter=filter,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata,
            include_values=include_values
        )

    async def _hybrid_similarity(self, query: Embeddings, top_k=3, alpha=1, filter=None, namespace=None, include_metadata=True, parse_model=True, include_values=False):
        embs = self.embeddings_avg(query, alpha)
        return await asyncio.to_thread(
            self.index.query,
            vector=embs.dense,
            sparse_vector=embs.sparse,
            filter=filter,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata,
            include_values=include_values
        )


    async def get_many(self, top_k=100, namespace=None, include_metadata=True, parse_model=True, include_values=False):
        namespace = namespace or self.namespace
        vector = [0 for i in range(self.dimension)]
        results = await asyncio.to_thread(self.index.query,
            vector=vector,
            filter=None,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata,
            include_values=include_values
        )
        return self._pack_result(results, parse_model=parse_model)
    

    async def update(self, id: str, metadata: Any, namespace=None):
        namespace = namespace or self.namespace        
        metadata = self.serialize_metadata(metadata)
        update_res = await asyncio.to_thread(self.index.update, id, set_metadata=metadata, namespace=namespace )
        return update_res
    

    def _pack_result(self, records, parse_model=True):
        return [PineconeSearchResult(
                id=record.id,
                score=record.score,
                metadata=self.deserialize_metadata(record.metadata, parse_model=parse_model),
                dense_vec=record.values,
                sparse_vec=record.sparse_values
            ) for record in  records.matches]
        
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


    
    # def update(self, id: str, metadata: Any, namespace=None):
    #     metadata = self.validate_metadata_model(metadata)
    #     namespace = namespace or self.namespace
    #     update_res = self.index.update(id, set_metadata=metadata, namespace=namespace )
    #     return update_res


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