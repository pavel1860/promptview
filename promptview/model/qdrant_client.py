from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Literal, TypedDict
from uuid import uuid4
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException
from qdrant_client.models import (DatetimeRange, Distance, FieldCondition,
                                  Filter, NamedSparseVector, NamedVector,
                                  PointStruct, Range, SearchRequest,
                                  SparseIndexParams, SparseVector,
                                  SparseVectorParams, VectorParams)
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client import models
import grpc
import os
import itertools

from .fields import VectorSpaceMetrics



if TYPE_CHECKING:
    from .resource_manager import VectorSpace
from .query import QueryFilter, FieldComparable, FieldOp, QueryOp, QuerySet


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
                        

            return models.Filter(
                must_not=must_not,
                must=must
            )


class OrderBy(TypedDict):
    key: str
    direction: Literal["asc", "desc"]
    start_from: int | float | datetime


def metrics_to_qdrant(metric: VectorSpaceMetrics):
    if metric == VectorSpaceMetrics.COSINE:
        return models.Distance.COSINE
    elif metric == VectorSpaceMetrics.EUCLIDEAN:
        return Distance.EUCLID
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
    
    
    # async def scroll(
    #         self,
    #         collection_name: str, 
    #         filters: Any,  
    #         ids: List[str | int] | None=None, 
    #         top_k: int=10, 
    #         offset: int=0,
    #         with_payload=False, 
    #         with_vectors=False, 
    #         order_by: OrderBy | str | None=None,
    #     ):
    #     filter_ = None
    #     if ids is not None:
    #         # top_k: int | None = None
    #         filter_ = models.Filter(
    #             must=[
    #                 models.HasIdCondition(has_id=ids)
    #             ],
    #         )
    #     query = Query()
    #     if filters:
    #         must_not, must = query.parse_filter(filters)
    #         filter_ = models.Filter(
    #             must_not=must_not,
    #             must=must
    #         )
    #     if order_by:
    #         if type(order_by) == str:
    #             pass                
    #         elif type(order_by) == dict:
    #             order_by = models.OrderBy(
    #                 key=order_by.get("key"),
    #                 direction=order_by.get("direction", "desc"), # type: ignore
    #                 start_from=order_by.get("start_from", None),  # start from this value
    #             )
    #             offset = None
    #         else:
    #             raise ValueError("order_by must be a string or a dict.")
        
            
    #     recs, _ = await self.client.scroll(
    #         collection_name=collection_name,
    #         # scroll_filter=filter_,
    #         limit=top_k,
    #         offset=offset,
    #         with_payload=with_payload,
    #         with_vectors=with_vectors,
    #         # order_by=order_by # type: ignore
    #     )
    #     return recs
    
    async def retrieve(
        self,
        collection_name: str,
        ids: List[str] | List[int],
        partitions: dict[str, str] | None = None
    ):
        recs = await self.client.retrieve(
            collection_name=collection_name,
            ids=ids
        )
        return recs
    
    
    async def scroll(
            self,
            collection_name: str, 
            filters: Any,  
            ids: List[str | int] | None=None, 
            limit: int=10, 
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
        if filters:
            filter_ = self.transform_filters(filters)
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
        
            
        recs, a = await self.client.scroll(
            collection_name=collection_name,
            scroll_filter=filter_,
            limit=limit,
            offset=offset,
            with_payload=with_payload,
            with_vectors=with_vectors,
            order_by=order_by # type: ignore
        )
        return recs
    
    
    async def query_points(
        self,
        collection_name: str, 
        vectors: dict[str, Any],
        filters: Any,  
        ids: List[str | int] | None=None, 
        limit: int =10, 
        offset: int=0,
        with_payload=False, 
        with_vectors=False, 
        order_by: OrderBy | str | None=None,
    ):        
        filter_ = None
        if filters:
            # filter_ = Query().parse_filter(filters)
            filter_ = self.transform_filters(filters)
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
        using, query = next(iter(vectors.items()))
        recs = await self.client.query_points(
            collection_name=collection_name,
            query=query,
            using=using,
            query_filter=filter_,
            limit=limit,
            offset=offset,
            with_payload=with_payload,
            with_vectors=with_vectors,            
        )        
        return recs
    
    
    async def prefetch(
        self,
        collection_name: str, 
        vectors: dict[str, Any],
        filters: Any,  
        ids: List[str | int] | None=None, 
        limit: int=10, 
        offset: int=0,
        with_payload=False, 
        with_vectors=False, 
        order_by: OrderBy | str | None=None,
    ):        
        filter_ = None
        if filters:
            # filter_ = Query().parse_filter(filters)
            filter_ = self.transform_filters(filters)
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
        using, query = next(iter(vectors.items()))
        recs = await self.client.prefetch(
            collection_name=collection_name,
            query=query,
            using=using,
            query_filter=filter_,
            limit=limit,
            offset=offset,
            with_payload=with_payload,
            with_vectors=with_vectors,            
        )
        
        return recs
    
    
    async def search(
            self, 
            collection_name: str, 
            query, 
            limit=3, 
            filters=None, 
            alpha=None, 
            with_vectors=False, 
            fussion: Literal["RRF", "RSF"] | None = None,
            retry: int=3,
            base_delay=1, 
            max_delay=8,
            threshold: float | None=None,
            order_by: OrderBy | str | None=None,
        ):
        filter_ = None
        if filters:
            # filter_ = Query().parse_filter(filters)
            filter_ = self.transform_filters(filters)
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
        
        recs = await self.client.search(
            collection_name=collection_name,
            query_vector=NamedVector(
                name="dense",
                vector=query["dense"]
            ),
            query_filter=filter_,
            limit=limit,            
            with_payload=True,
            with_vectors=with_vectors,
            score_threshold=threshold,
        )
        return recs
    
    
    async def update_payload(self, collection_name: str, ids: List[str] | List[int], payload: Dict[str, Any]):
        if ids:
            points = ids
        else:
            raise ValueError("ids must be provided.")
        await self.client.set_payload(
            collection_name=collection_name,
            payload=payload,
            points=points,
            # points=models.Filter(
            #     must=[
            #         models.FieldCondition(
            #             key="color",
            #             match=models.MatchValue(value="red"),
            #         ),
            #     ],
            # ),
        )    
    
    
    async def delete(self, collection_name: str, ids: List[str] | List[int] | None = None, filters: Any | None = None):
        if ids:        
            return await self.client.delete(
                collection_name=collection_name,
                points_selector=models.PointIdsList(
                    points=ids, # type: ignore
                ),
            )
        elif filters:
            query_filter = self.transform_filters(filters)
            return await self.client.delete(
                collection_name=collection_name,
                points_selector=models.FilterSelector(
                    filter=query_filter
                )
            )
        else:
            raise ValueError("Either ids or filters must be provided.")



    async def create_collection(self, collection_name: str , vector_spaces: list["VectorSpace"], indices: list[dict[str, str]] | None=None):
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
    
    def _build_vector_query(self, vec_name, vector):
        if isinstance(vector, dict):                
            return models.SparseVector(**vector)                          
        else:
            return vector.tolist()
            # return models.NamedVector(name=vec_name, vector=vector)
          
            
    async def execute_query(self, collection_name: str, query_set: QuerySet):
        if query_set.query_type == "vector":
            return await self.execute_vector_query(collection_name, query_set)
        if query_set.query_type == "id":
            return await self.execute_vector_query(collection_name, query_set)
        elif query_set.query_type == "scroll":
            return await self.execute_scroll(collection_name, query_set)
    
    
    async def execute_vector_query(self, collection_name: str, query_set: QuerySet):
        
        query, prefetch, query_filter, using, limit, offset, threshold = self._parse_query(query_set)
        
        order_by = None
        if query_set._order_by:
            prefetch = models.Prefetch(
                    prefetch=prefetch,
                    query=query,
                    using=using,
                    filter=query_filter,
                    limit=limit,
                    # offset=offset,
                )
            order_by = self._build_order_by(query_set)
            query = models.OrderByQuery(
                order_by=order_by,
            )
            using = None
            limit = None
            offset = None
            threshold=None
            
        
        recs = await self.client.query_points(
            collection_name=collection_name,
            prefetch=prefetch,
            query=query,
            using=using,
            query_filter=query_filter,
            limit=limit,
            offset=offset,
            score_threshold=threshold,
            # order_by=order_by,
        )
        return recs.points
    
    async def execute_scroll(self, collection_name: str, query_set: QuerySet):        
        _, _, scroll_filter, _, limit, offset, _ = self._parse_query(query_set)
        
        order_by = None
        if query_set._order_by is not None:
            order_by = self._build_order_by(query_set)
            offset = None
        
        recs, a = await self.client.scroll(
            collection_name=collection_name,
            scroll_filter=scroll_filter,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=True,
            order_by=order_by
        )
        return recs
    
    def _build_order_by(self, query_set: QuerySet, as_query=False)-> models.OrderBy | str:
        if type(query_set._order_by) == str:
            return query_set._order_by
        elif type(query_set._order_by) == dict:            
            return models.OrderBy(
                key=query_set._order_by.get("key"),# type: ignore
                direction=query_set._order_by.get("direction", "desc"),
                start_from=query_set._order_by.get("start_from", None),  # start from this value
            )
        else:
            raise ValueError("order_by must be a string or a dict.")
    
    def _parse_query(self, query_set: QuerySet):
        query_filter = None
        prefetch = None
        query = None
        using = None
        order_by = None
        threshold = None
        # if query_set._filters:
        #     query_filter = self.transform_filters(query_set._filters)
        # if subspace:= query_set.get_subspace():
        #     if query_filter is not None:
        #         query_filter.must.append(
        #             models.FieldCondition(
        #                 key=subspace.field,
        #                 match=models.MatchValue(value=subspace)
        #             )
        #         )
        #     else:
        #         query_filter = models.Filter(
        #             must=[
        #                 models.FieldCondition(
        #                     key="_subspace",
        #                     match=models.MatchValue(value=subspace)
        #                 )
        #             ]
        #         )
        if query_set._filters or query_set._partitions:
            query_filter = self._parse_partition_query_filters(query_set)
                    
        if query_set._prefetch:
            prefetch = [self._parse_prefetch(q) for q in query_set._prefetch]        
        if query_set.query_type == "vector":            
            if not query_set._vector_query:
                raise ValueError("Vector query not provided.")
            threshold = query_set._vector_query.threshold
            if len(query_set._vector_query) == 1:
                # for vec_name, vector in query_set._vector_query.vector_lookup.items():
                vec_name, vector = query_set._vector_query.first()
                query = self._build_vector_query(vec_name, vector)
                using = vec_name
            else:
                prefetch = []
                # for vec_name, vector in query_set._vector_query.vector_lookup.items():
                for vec_name, vector in query_set._vector_query:
                    vec_query = self._build_vector_query(vec_name, vector)
                    prefetch.append(
                        models.Prefetch(
                            query=vec_query,
                            using=vec_name,
                            limit=query_set._limit,
                        )
                    )                                    
                if query_set._fusion == "dbsf":
                    query = models.FusionQuery(fusion=models.Fusion.DBSF)
                else:
                    query = models.FusionQuery(fusion=models.Fusion.RRF)
        elif query_set.query_type == "fusion":
            if query_set._fusion == "rff":
                query = models.FusionQuery(fusion=models.Fusion.RRF)
            elif query_set._fusion == "dbsf":
                query = models.FusionQuery(fusion=models.Fusion.DBSF)                           
        elif query_set.query_type == "id":
            query = query_set._ids
                
        # if query_set._order_by:
        return query, prefetch, query_filter, using, query_set._limit, query_set._offset, threshold
    
    
    def _parse_prefetch(self, query_set: QuerySet):
        query, prefetch, query_filter, using, limit, offset, threshold = self._parse_query(query_set)
        # vec_name, _ = query_set._vector_query.first()
        return models.Prefetch(
            query=query,
            using=using,
            limit=limit,
            filter=query_filter,
            prefetch=prefetch,
            score_threshold=threshold,
        )
        
    def _parse_partition_query_filters(self, query_set: QuerySet):
        query_filter = None
        if query_set._filters is not None:
            query_filter = self._parse_query_filter(query_set._filters)
        
        if query_set._partitions:
            partition_cond = [
                models.FieldCondition(
                    key=field,
                    match=models.MatchValue(value=value)
                ) if value is not None else models.IsNullCondition(
                        is_null=models.PayloadField(key=field)
                    )
                for field, value in query_set._partitions.items()
            ]
            if query_filter is None:
                query_filter= Filter(
                    must=partition_cond
                )
            else:
                if query_filter.must is None:
                    query_filter.must = partition_cond
                else:
                    query_filter.must = [*query_filter.must, *partition_cond]
        return query_filter
    
    
    def transform_filters(self, query_filters):
        return self._parse_query_filter(query_filters)
    
    def _parse_query_filter(self, query_filter: QueryFilter) -> Filter:
        """Recursively parse QueryFilter into Qdrant Filter object."""
        if isinstance(query_filter._operator, QueryOp):
            # Logical operators (AND/OR)
            if query_filter._operator == QueryOp.AND:
                return Filter(
                    must=[
                        self._parse_query_filter(query_filter._left),
                        self._parse_query_filter(query_filter._right)
                    ]
                )
            elif query_filter._operator == QueryOp.OR:
                return Filter(
                    should=[
                        self._parse_query_filter(query_filter._left),
                        self._parse_query_filter(query_filter._right)
                    ]
                )
        elif isinstance(query_filter._operator, FieldOp):
            # Field comparison operators
            if query_filter._operator == FieldOp.EQ:
                return Filter(
                    must=[
                        FieldCondition(key=query_filter.field.name, match=models.MatchValue(value=query_filter.value))
                    ]
                )
            elif query_filter._operator == FieldOp.NE:
                return Filter(
                    must_not=[
                        FieldCondition(key=query_filter.field.name, match=models.MatchValue(value=query_filter.value))
                    ]
                )
            elif query_filter._operator == FieldOp.RANGE:
                if query_filter.is_datetime():
                    return Filter(
                        must=[
                            FieldCondition(
                                key=query_filter.field.name,
                                range=DatetimeRange(lt=query_filter.value.lt, lte=query_filter.value.le, gt=query_filter.value.gt, gte=query_filter.value.ge)
                            )
                        ]
                    )
                else:
                    return Filter(
                        must=[
                            FieldCondition(
                                key=query_filter.field.name,
                                range=Range(lt=query_filter.value.lt, lte=query_filter.value.le, gt=query_filter.value.gt, gte=query_filter.value.ge)
                            )
                        ]
                    )
            elif query_filter._operator == FieldOp.IN:
                return Filter(
                    must=[
                        FieldCondition(key=query_filter.field.name, match=models.MatchAny(any=query_filter.value))
                    ]
                )
        else:
            raise ValueError(f"Unsupported operator: {query_filter._operator}")

    
    
    
    # def transform_filters2(self, query_filters):

    #     match_filters = {}

    #     not_match_filters = {}

    #     range_filters = {} 


    #     def traverse(query):
    #         if isinstance(query._operator, QueryOp):
    #             traverse(query._left)
    #             traverse( query._right)
    #             print(traverse)
    #         elif isinstance(query._operator, FieldOp):
    #             # if isinstance(query._left, FieldComparable):
    #             #     field = query._left
    #             #     value = query._right
    #             # elif isinstance(query._right, FieldComparable):
    #             #     field = query._right
    #             #     value = query._left
    #             # else:
    #             #     raise ValueError("No FieldComparable found")
    #             field, value = query.field, query.value
                
    #             if query._operator in [FieldOp.GT, FieldOp.GTE, FieldOp.LT, FieldOp.LTE]:
    #                 range_filter = range_filters.get(field.name)
    #                 if not range_filter:
    #                     range_filter = models.FieldCondition(
    #                         key=field.name,
    #                         range=models.DatetimeRange() if query.is_datetime() else models.Range()
    #                     )
    #                     range_filters[field.name] = range_filter
    #                 if query._operator == FieldOp.GT:
    #                     range_filter.range.gt = value
    #                 elif query._operator == FieldOp.GTE:
    #                     range_filter.range.gte = value
    #                 elif query._operator == FieldOp.LT:
    #                     range_filter.range.lt = value
    #                 elif query._operator == FieldOp.LTE:
    #                     range_filter.range.lte = value
    #                 # print("Range", field.name, query._operator, value)
    #             elif query._operator in [FieldOp.EQ]:
    #                 match_filter = range_filters.get(field.name)
    #                 if match_filter:
    #                     raise ValueError(f"Match filter already exists for field {field.name}")
    #                 match_filters[field.name] = models.FieldCondition(
    #                     key=field.name,
    #                     match=models.MatchValue(value=value)
    #                 )
    #                 print("Match", field.name, query._operator, value)
    #             elif query._operator in [FieldOp.NE]:
    #                 not_match_filters[field.name] = models.FieldCondition(
    #                     key=field.name,
    #                     match=models.MatchValue(value=value)
                        
    #                 )
    #                 print("Not Match", field.name, query._operator, value)
                    
    #         else:
    #             raise ValueError("Unknown operator")

    #     traverse(query_filters)

    #     model_filters = models.Filter(
    #             must=[f for f in match_filters.values()] + [ f for f in range_filters.values()],
    #             must_not=[ f for f in not_match_filters.values() ],        
    #         )
    #     return model_filters




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
    
    