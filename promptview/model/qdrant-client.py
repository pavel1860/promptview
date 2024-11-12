from datetime import datetime
from typing import Any, Dict
from qdrant_client import AsyncQdrantClient, QdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException
from qdrant_client.models import (DatetimeRange, Distance, FieldCondition,
                                  Filter, NamedSparseVector, NamedVector,
                                  PointStruct, Range, SearchRequest,
                                  SparseIndexParams, SparseVector,
                                  SparseVectorParams, VectorParams)
import os


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










class QdrantClient:
    
    
    def __init__(self, url=None, api_key=None, prefer_grpc=True):
        self.url = url or os.environ.get("QDRANT_URL")
        self.api_key = api_key or os.environ.get("QDRANT_API_KEY", None)
        self.client = AsyncQdrantClient(
            url=self.url,
            api_key=self.api_key,
            prefer_grpc=prefer_grpc,
        )
        
        
        
    async def add_documents(self, vectors, metadata: List[Dict | BaseModel], ids=None, namespace=None, batch_size=100):
        namespace = namespace or self.collection_name
        # metadata = [m.dict(exclude={'__orig_class__'}) if isinstance(m, BaseModel) else m for m in metadata]
        metadata = [m if isinstance(m, dict) else m.dict(exclude={'__orig_class__'}) for m in metadata]
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
            await self.client.upsert(
                collection_name=namespace,
                points=points
            )
            results += [
                VectorSearchResult(
                    id=p.id,
                    score=-1,
                    metadata=p.payload,
                    vector=p.vector
                ) 
                for p in points]        
        return results

        
    