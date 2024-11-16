from datetime import datetime
from typing import Any, Dict, List, Literal, TypedDict
from uuid import uuid4
from qdrant_client import AsyncQdrantClient, QdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException
from qdrant_client.models import (DatetimeRange, Distance, FieldCondition,
                                  Filter, NamedSparseVector, NamedVector,
                                  PointStruct, Range, SearchRequest,
                                  SparseIndexParams, SparseVector,
                                  SparseVectorParams, VectorParams)
from qdrant_client.http.exceptions import UnexpectedResponse
import grpc
import os
import itertools

from promptview.model.fields import VectorSpaceMetrics
from promptview.model.namespace import VectorSpace


def chunks(iterable, batch_size=100):
    """A helper function to break an iterable into chunks of size batch_size."""
    it = iter(iterable)
    chunk = tuple(itertools.islice(it, batch_size))
    while chunk:
        yield chunk
        chunk = tuple(itertools.islice(it, batch_size))



class Query:

    def parse_filter(self, filters: Dict[str, Any]):

            must = []
            must_not = []

            def is_range(value):    
                for k, v in value.items():
                    if k not in [">", ">=", "<", "<="]:
                        return False
                return True

            def unpack_range(value):
                gt=value.get('>', None)
                gte=value.get('>=', None)
                lt=value.get('<', None)
                lte=value.get('<=', None)
                if type(gt) == datetime or type(gte) == datetime or type(lt) == datetime or type(lte) == datetime:
                    gt = gt.isoformat(timespec='seconds') if gt else None
                    gte = gte.isoformat(timespec='seconds') if gte else None
                    lt = lt.isoformat(timespec='seconds') if lt else None
                    lte = lte.isoformat(timespec='seconds') if lte else None
                    return models.DatetimeRange(gt=gt,gte=gte,lt=lt,lte=lte)            
                return models.Range(gt=gt,gte=gte,lt=lt,lte=lte)

            for field, value in filters.items():
                if type(value) == dict:
                    if is_range(value):
                        must.append(models.FieldCondition(key=field, range=unpack_range(value)))
                    else:
                        for k, v in value.items():
                            if k == "$ne":
                                must_not.append(models.FieldCondition(key=field, match=models.MatchValue(value=v)))
                            elif k == "$eq":
                                must.append(models.FieldCondition(key=field, match=models.MatchValue(value=v)))
                else:
                    if type(value) == list:
                        must.append(models.FieldCondition(key=field, match=models.MatchAny(any=value)))
                    else:
                        must.append(models.FieldCondition(key=field, match=models.MatchValue(value=value)))
                        

            return must_not, must


class OrderBy(TypedDict):
    key: str
    direction: Literal["asc", "desc"]
    start_from: int | float | datetime


def metrics_to_qdrant(metric: VectorSpaceMetrics):
    if metric == VectorSpaceMetrics.COSINE:
        return models.Distance.COSINE
    elif metric == VectorSpaceMetrics.EUCLIDEAN:
        return Distance.EUCLIDEAN
    elif metric == VectorSpaceMetrics.MANHATTAN:
        return Distance.MANHATTAN
    else:
        raise ValueError(f"Unsupported metric {metric}")



class QdrantResult:
    status: str
    ids: str
    
    
    





class QdrantClient:
    
    
    def __init__(self, url=None, api_key=None, prefer_grpc=True):
        self.url = url or os.environ.get("QDRANT_URL")
        self.api_key = api_key or os.environ.get("QDRANT_API_KEY", None)
        self.client = AsyncQdrantClient(
            url=self.url,
            api_key=self.api_key,
            prefer_grpc=prefer_grpc,
        )
        
    async def close(self):
        await self.client.close()
            
        
    async def upsert(self, namespace: str, vectors, metadata: List[Dict], ids=None, batch_size=100):
        if not ids:
            ids = [str(uuid4()) for i in range(len(vectors))]
        
        results = []
        for vector_chunk in chunks(zip(ids, vectors, metadata), batch_size=batch_size):
            points = [
                PointStruct(
                    id=id_,
                    payload=meta,
                    vector=vec
                )
                for id_, vec, meta in vector_chunk]
            upsert_result = await self.client.upsert(
                collection_name=namespace,
                points=points
            )
            results += points
            # results += [
            #     QdrantResult(
            #         id=p.id,
            #         score=-1,
            #         metadata=p.payload,
            #         vector=p.vector
            #     ) 
            #     for p in points]        
        return results

        
    
    
    async def scroll(
            self,
            collection_name: str, 
            filters: Any,  
            ids: List[str | int] | None=None, 
            top_k: int=10, 
            offset: int=0,
            with_payload=False, 
            with_vectors=False, 
            order_by: OrderBy | str | None=None,
        ):
        filter_ = None
        if ids is not None:
            # top_k: int | None = None
            filter_ = models.Filter(
                must=[
                    models.HasIdCondition(has_id=ids)
                ],
            )
        query = Query()
        if filters:
            must_not, must = query.parse_filter(filters)
            filter_ = models.Filter(
                must_not=must_not,
                must=must
            )
        if order_by:
            if type(order_by) == str:
                pass                
            elif type(order_by) == dict:
                order_by = models.OrderBy(
                    key=order_by.get("key"),
                    direction=order_by.get("direction", "desc"), # type: ignore
                    start_from=order_by.get("start_from", None),  # start from this value
                )
                offset = None
            else:
                raise ValueError("order_by must be a string or a dict.")
        
            
        recs, _ = await self.client.scroll(
            collection_name=collection_name,
            # scroll_filter=filter_,
            limit=top_k,
            offset=offset,
            with_payload=with_payload,
            with_vectors=with_vectors,
            # order_by=order_by # type: ignore
        )
        return recs
    
    
    
    
    async def delete(self, filters):
        if not filters:
            raise ValueError("filters must be provided. to delete all documents, use delete_collection method.")
        if filters is not None:
            must_not, must = self.parse_filter(filters)
            filter_ = models.Filter(
                must_not=must_not,
                must=must
            )
        
        res = await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=filter_
            )
        )
        return res




    async def create_collection(self, collection_name: str , vector_spaces: list[VectorSpace], indices: list[dict[str, str]]=None):
        http_client = AsyncQdrantClient(
            url=self.url,
            api_key=self.api_key,
            prefer_grpc=False,
        )
        vector_config = {}
        sparse_vector_config = {}
        for vs in vector_spaces:
            vectorizer = vs.vectorizer
            if vectorizer.type == "dense":                
                vector_config[vs.name] = VectorParams(
                    size=vectorizer.size, 
                    distance=metrics_to_qdrant(vs.metric)
                )
            elif vectorizer.type == "sparse":
                sparse_vector_config[vs.name] = SparseVectorParams(
                    index=models.models.SparseIndexParams()
                )
        create_res = await http_client.recreate_collection(
            collection_name=collection_name,
            vectors_config=vector_config,
            sparse_vectors_config=sparse_vector_config           
        )
        if indices:
            for index in indices:
                try:
                    await http_client.create_payload_index(
                        collection_name=collection_name,
                        field_name=index['field'],
                        field_schema=index['schema']
                    )
                except Exception as e:
                    raise e
        return create_res



    async def delete_collection(self, collection_name: str | None =None):
        await self.client.delete_collection(collection_name=collection_name)
        
        
    async def get_collections(self):
        return await self.client.get_collections()
    
    
    async def get_collection(self, collection_name: str, raise_error=True):
        try:
            return await self.client.get_collection(collection_name)
        except (UnexpectedResponse, grpc.aio._call.AioRpcError) as e:
            if raise_error:
                raise e
            return None
    