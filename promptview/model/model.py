import asyncio
from datetime import datetime
from enum import Enum
import inspect
import json
from typing import Any, Dict, List, Optional, Type, TypeVar,  get_args, get_origin
from uuid import uuid4
from promptview.model.query import FieldComparable
from promptview.model.vectors.base_vectorizer import BaseVectorizer
from promptview.model.fields import VectorSpaceMetrics, get_model_indices
from promptview.utils.function_utils import call_function
from promptview.utils.model_utils import unpack_list_model, is_list_model
from promptview.utils.datetime_utils import get_int_timestamp
from pydantic import PrivateAttr, create_model, ConfigDict, BaseModel, Field
from pydantic.fields import FieldInfo
from pydantic._internal._model_construction import ModelMetaclass

from .resource_manager import VectorSpace, connection_manager



def make_optional(model: BaseModel | str) -> BaseModel:
    if model == str:
        return Optional[str]
    optional_fields = {k: (Optional[v], None) for k, v in model.__annotations__.items()}
    return create_model(
        model.__name__, 
        **optional_fields,         
        __config__=ConfigDict(arbitrary_types_allowed=True)
        # __config__=Config
    )


def get_model_fields(model_instance, model_class):
    try:
        fields = {field: getattr(model_instance, field) for field in model_class.__fields__.keys()}
        return model_class(**fields)
    except:
        return None



MetadataArg = BaseModel | dict | str | None

class DefaultInput(BaseModel):
    input: str

class DefaultOutput(BaseModel):
    output: str


TInput = TypeVar('TInput', bound=BaseModel | str | None)
TOutput = TypeVar('TOutput', bound=BaseModel | str )
TMetadata = TypeVar('TMetadata', bound=BaseModel)

def serialize_field(field):
    if field is None:
        return None
    if type(field) == str:
        return field
    if isinstance(field, BaseModel):
        return field.dict()


def copy_field(field):
    if field is None:
        return None
    if type(field) == str:
        return field
    if isinstance(field, BaseModel):
        return field.model_copy()


class ModelManager:
    
    _assets: Dict[str, "Model"] = {}
    
    def __init__(self):
        self._assets = {}
        
    def get_asset(self, asset_name: str):
        return self._assets.get(asset_name, None)
    
    def add_asset(self, asset: "Model"):
        self._assets[asset.__name__] = asset
        return asset
        

model_manager = ModelManager()  



    

# AssetBase = TypeVar('AssetBase')



MODEL = TypeVar("MODEL", bound="Model")



class Relation:
    
    def __init__(self, cls: Type["Model"], partitions: dict):
        self._cls = cls
        self._partitions = partitions
        
    async def all(cls, partitions=None, limit=10, start_from=None, offset=0, ascending=False, ids=None):
        partitions = partitions or {}
        recs = await cls.get_assets(top_k=limit, filters=partitions, start_from=start_from, offset=offset, ascending=ascending, ids=ids)
        return recs
    
    async def add(self):
        pass
    
    async def get_or_create(self):
        pass
    
    async def upsert(self):
        pass
    
    async def create(self,):
        pass
    
    async def first(self, partitions=None):
        partitions = partitions or {}        
        return await self._cls.get_assets(top_k=1, filters=partitions, ascending=True)
        

    async def last(self, partitions=None):
        partitions = partitions or {}
        return await self._cls.get_assets(top_k=1, filters=partitions, ascending=False)
        





class ModelMeta(ModelMetaclass, type):
    
    # def __new__(cls, name, bases, dct):
    #     print("Creating class", name)
    #     return super().__new__(cls, name, bases, dct)
    
    def __new__(cls, name, bases, dct):
        print("Creating class", name)
        cls_partitions = {}
        default_temporal_field = None
        default_temporal_type = None
        namespace = None
        if name != "Model":
            #? add model partition
            model_base = bases[0]
            if model_base == Model:
                dct["_subspace"] = None
            else: 
                dct["_subspace"] = name                
            
            for field, field_type in dct.items():
                #? temporal field extraction
                if inspect.isclass(field_type.__class__):
                    if isinstance(field_type, FieldInfo):
                        if field_type.json_schema_extra.get("auto_now_add", None):
                            default_temporal_field = field
                            default_temporal_type = field_type
                    #? vector space extraction                   
                    
                    if field == "VectorSpace":
                        vector_spaces = []
                        vectorizers = field_type.__annotations__
                        for vec_name, vec_cls in vectorizers.items():
                            if not issubclass(vec_cls, BaseVectorizer):
                                raise ValueError(f"Vector Space {vec_name} must be of type BaseVectorizer")
                            vector_spaces.append(
                                VectorSpace(
                                    name=vec_name,
                                    vectorizer_cls=vec_cls,
                                    metric=VectorSpaceMetrics.COSINE                                
                                ))
                            # vectorizers_manager.add_vectorizer(vec_name, vec_cls)
                        #? namespace and indices extraction
                        namespace = name                        
                        indices = get_model_indices(dct)
                        connection_manager.add_namespace(
                            namespace=namespace,
                            # subspace=dct.get("_subspace"),
                            vector_spaces=vector_spaces,
                            indices=indices
                        )
            if dct.get("_subspace", None):
                if not hasattr(bases[0], "_namespace"):
                    raise ValueError(f"Namespace not defined in base class of {name}")
                indices = get_model_indices(dct)
                connection_manager.add_subspace(bases[0]._namespace.default, dct["_subspace"], indices)
                
            #? partition extraction
            if annotations:= dct.get("__annotations__", None):
                for field, field_type in annotations.items():       
                    field_origin = get_origin(field_type)
                    if field_origin == list:
                        target_type = unpack_list_model(field_type)
                    else:
                        target_type = field_type
                    if inspect.isclass(target_type): 
                        if issubclass(target_type, Model):
                            field_info = dct.get(field)                            
                            if not field_info:
                                raise ValueError(f"Field {field} is not defined")
                            partition = field_info.json_schema_extra.get("partition")
                            if not partition:
                                raise ValueError(f"Model Field {field} does not have partition")
                            cls_partitions[field] = {
                                "type": target_type,
                                "origin": field_origin,
                                "partition": partition,
                                "field": field
                            }
                            field_info.default_factory = lambda: Relation(target_type, partition)  
                            print("Found",field, partition)
                
            dct["_partitions"] = cls_partitions
            dct["_default_temporal_field"] = default_temporal_field
            if namespace:
                dct["_namespace"] = namespace
            # dct["_vectorizers"] = connection_manager.get_vectorizers(namespace)
        asset_inst = super().__new__(cls, name, bases, dct)
        if name != "Model":
            model_manager.add_asset(asset_inst)
        return asset_inst
    
    
    # def __getattr__(cls, name):
    #     if field_info:= cls.model_fields.get(name, None):
    #         # print("Getting attribute",cls.__name__, name)
    #         return FieldComparable(name, field_info)
    #     return super().__getattr__(name)


class Model(BaseModel, metaclass=ModelMeta):
    _id: str = PrivateAttr(default_factory=lambda: str(uuid4()))
    _score: float = PrivateAttr(default=-1)
    _partitions: dict[str, str] = PrivateAttr(default_factory=dict)
    _default_temporal_field: str = PrivateAttr(default=None)
    _namespace: str = PrivateAttr(default=None)
    # _vectorizers: dict[str, BaseVectorizer] = PrivateAttr(default_factory=dict)
    
    class Config:
        arbitrary_types_allowed = True
    
    
    def __init__(self,_id=None, _score=None, **data):
        super().__init__(**data)
        if _id:
            self._id = _id
        if _score:
            self._score = _score
    
        
    @property
    def id(self):
        return self._id
    
    @property
    def score(self):
        return self._score
    
    
    
    @classmethod
    async def get_client(cls):
        ns = await connection_manager.get_namespace(cls._namespace.default)
        return ns.conn
        
    
    def _payload_dump(self):
        dump = self.model_dump()
        dump["_subspace"] = self._subspace
        return dump
        
    # async def verify_namespace(self):
        # await self.rag_documents.verify_namespace()
    
    @classmethod
    async def _vectorize(cls, obj):
        key = obj.model_dump_json()
        vector_list = await asyncio.gather([
            vec.embed([key]) for vec in cls._vectorizers.values()
        ])
        return {vec_name: vec for vec_name, vec in zip(cls._vectorizers.keys(), vector_list)}
    
    
    # async def vectorize(self, key: str):
    #     ns = await connection_manager.get_namespace(self._namespace)        
    #     key = self.model_dump_json()
    #     vector_list = await asyncio.gather(*[
    #         vs.vectorizer.embed_documents([key]) for _, vs in ns.vector_spaces.items()
    #     ])        
    #     return {vec_name: vec[0] for vec_name, vec in zip(ns.vector_spaces.keys(), vector_list)}
    async def vectorize(self, vectorizers: dict[str, BaseVectorizer]):        
        key = self.model_dump_json()
        vector_list = await asyncio.gather(*[
            vectorizer.embed_documents([key]) for _, vectorizer in vectorizers.items()
        ])        
        return {vec_name: vec[0] for vec_name, vec in zip(vectorizers.keys(), vector_list)}

    async def _call_vectorize(self):
        ns = await connection_manager.get_namespace(self._namespace)
        vectorizers = {name: vs.vectorizer for name, vs in  ns.vector_spaces.items()}
        return await call_function(self.vectorize, vectorizers=vectorizers)

    
    @classmethod
    async def _call_vectorize_query(cls, query: str, use: str=None):
        namespace = cls._namespace.default
        ns = await connection_manager.get_namespace(namespace)
        vectorizers = {name: vs.vectorizer for name, vs in  ns.vector_spaces.items() if name == use}
        vector_list = await asyncio.gather(*[
            vectorizer.embed_documents([query]) for _, vectorizer in vectorizers.items()
        ])
        return {vec_name: vec[0] for vec_name, vec in zip(vectorizers.keys(), vector_list)}
        
    async def save(self):
        if not self._namespace:
            raise ValueError("Namespace not defined")
        namespace = await connection_manager.get_namespace(self._namespace)        
        # key = self.model_dump_json()
        vectors = await self._call_vectorize()
        metadata = self._payload_dump()
        res = await namespace.conn.upsert(
                namespace=self._namespace,
                vectors=[vectors],
                metadata=[metadata],
                ids=[self._id]
            )
        return self
    
    async def delete(self):
        db_conn = await connection_manager.get_collection_conn(self.__class__)
        return await db_conn.delete_documents(ids=[self._id])
    
    
    @classmethod
    def _pack_search_result(cls, search_result):
        return cls(
            _id=search_result.id,
            _score=search_result.score if hasattr(search_result, "score") else -1,
            **search_result.payload
        )
        
    @classmethod
    def _get_default_temporal_field(cls):
        if cls._default_temporal_field.default is not None:
            return cls._default_temporal_field.default
        else:
            parent_field = cls.__bases__[0]._get_default_temporal_field()            
            return parent_field
    
    
    @classmethod
    async def get_assets(cls, top_k=10, filters=None, start_from=None, offset=0, ascending=False, ids=None):
        sort_key = cls._get_default_temporal_field()
        if not sort_key:
            raise ValueError("Temporal Field not defined")
        order_by = {
            "key": sort_key,
            "direction": "asc" if ascending else "desc",
            "start_from": start_from
        }
        namespace = cls._namespace.default
        ns = await connection_manager.get_namespace(namespace)
        res = await ns.conn.scroll2(
            collection_name=namespace,
            top_k=top_k,
            filters=filters,
            order_by=order_by,
            offset=offset,
            ids=ids,
            with_payload=True,
            with_vectors=True
        )
        # res = await rag_documents.get_documents(top_k=top_k, filters=filters, order_by=order_by, offset=offset, ids=ids, with_vectors=True)
        return [cls._pack_search_result(r) for r in res]
    
    @classmethod
    async def similar(
        cls, 
        query: str, 
        top_k=10, 
        filters=None, 
        use: str=None,
        threshold: float | None=None
    ):
        namespace = cls._namespace.default
        vector = await cls._call_vectorize_query(query, use=use)
        ns = await connection_manager.get_namespace(namespace)
        res = await ns.conn.search(
            namespace,
            query=vector,
            top_k=top_k,
            filters=filters,
            threshold=threshold
        )
        return [cls._pack_search_result(r) for r in res]
        
    
    
    @classmethod
    async def all(cls, partitions=None, limit=10, start_from=None, offset=0, ascending=False, ids=None):
        partitions = partitions or {}
        recs = await cls.get_assets(top_k=limit, filters=partitions, start_from=start_from, offset=offset, ascending=ascending, ids=ids)
        return recs
    
    @classmethod
    async def add(cls: Type[MODEL]):
        pass
    
    
    @classmethod
    async def get_or_create(cls: Type[MODEL]):
        pass
    
    @classmethod
    async def upsert(cls: Type[MODEL]):
        pass
    
    @classmethod
    async def create(cls: Type[MODEL]):
        pass
    
    @classmethod
    async def first(cls: Type[MODEL], partitions=None):
        partitions = partitions or {}
        res = await cls.get_assets(top_k=1, filters=partitions, ascending=True)
        if len(res) == 0:
            return None
        return res[0]
    
    @classmethod
    async def last(cls: Type[MODEL], partitions=None):
        partitions = partitions or {}
        res = await cls.get_assets(top_k=1, filters=partitions, ascending=False)
        if len(res) == 0:
            return None
        return res[0]
        # partitions.update(self.partitions) #TODO need to understand how to get partitions
    
    
    
    # async def get(self, partitions=None, limit=1, start_from=None, ascending=False, with_metadata=False):
    #     partitions = partitions or {}
    #     partitions.update(self.partitions)
    #     res = await self.get_assets(top_k=limit, filters=partitions, start_from=start_from, ascending=ascending)
    #     if limit == 1:
    #         if len(res) == 0:
    #             return None                
    #         return res[0] if with_metadata else res[0].output
    #     return res if with_metadata else [r.output for r in res]
    
        
    # async def get_or_create(self, partitions=None, default=None, limit=1):
    #     partitions = partitions or {}
    #     partitions.update(self.partitions)
    #     default = default or self.output_class()
    #     res = await self.get_assets(top_k=limit, filters=partitions)
    #     if len(res) == 0:
    #         res = await self.add(default)
    #         return self._pack_record(res)
            
    #     return self._pack_record(res[0])
    
    
    # async def last(self, partitions=None):
    #     partitions = partitions or {}
    #     partitions.update(self.partitions)
    #     res = await self.get_assets(top_k=1, filters=partitions, ascending=False)
    #     if len(res) == 0:
    #         return None
    #     return self._pack_record(res[0])
    
    
    # async def one(self, partitions=None, start_from=None, ascending=False):
    #     partitions = partitions or {}
    #     partitions.update(self.partitions)
    #     res = await self.get_assets(top_k=1, filters=partitions, start_from=start_from, ascending=ascending)
    #     if len(res) == 0:
    #         return None
    #     return self._pack_record(res[0])
    
    
    # async def get_many(self, partitions=None, limit=10, start_from=None, ascending=False):
    #     partitions = partitions or {}
    #     partitions.update(self.partitions)
    #     res = await self.get_assets(top_k=limit, filters=partitions, start_from=start_from, ascending=ascending)
    #     return [self._pack_record(r) for r in res]
    
    
    # def from_json(self, data: dict):
    #     return self._search_result_class(
    #         # id=data["id"],
    #         # vector=data["vector"],
    #         # created_at=data["created_at"],
    #         # updated_at=data["created_at"],
    #         input_class=self.input_class,
    #         metadata_class=self.output_class,
    #         namespace=self.rag_documents.namespace,
    #         **data
    #     )
    
    # async def update_output(self, output: dict, ids: list[str] | None=None):
    #     vs = self.rag_documents.vector_store.client
    #     points = ids or None
    #     res = await vs.set_payload(
    #         collection_name="SessionAsset",
    #         key="output",
    #         payload=output,
    #         points=points
    #     )
    #     return res 
    
    # async def delete(self, assets=None, partitions=None, ids=None):
    #     if assets:
    #         if not isinstance(assets, List):
    #             assets = [assets]
    #         ids = []
    #         for a in assets:
    #             if not isinstance(a, AssetSearchResult):
    #                 raise ValueError("Asset must be of type AssetSearchResult")
    #             ids.append(a.id)
    #     partitions = partitions or {}
    #     partitions.update(self.partitions)
    #     return await self.rag_documents.delete_documents(ids=ids, filters=partitions)
    
    
    # def _pack_result(self, r):
    #     if self.input_class is None:
    #         return AssetSearchResult[None, self.output_class, self.metadata_class](
    #             id=r.id, 
    #             vector=r.vector,
    #             # input=r.metadata.input,
    #             output=r.metadata.output,
    #             metadata=r.metadata.metadata,                
    #             # asset_input_date=r.metadata.asset_input_date,   
    #             asset_output_date=r.metadata.asset_output_date,  
    #             asset_update_ts=r.metadata.asset_update_ts,                    
    #         )

        # return AssetSearchResult[self.input_class, self.output_class, self.metadata_class](
        #         id=r.id, 
        #         vector=r.vector,
        #         input=r.metadata.input,
        #         output=r.metadata.output,
        #         metadata=r.metadata.metadata,                
        #         asset_input_date=r.metadata.asset_input_date,   
        #         asset_output_date=r.metadata.asset_output_date,  
        #         asset_update_ts=r.metadata.asset_update_ts,                    
        #     ) 

    # async def copy_assets(self, assets: List[AssetSearchResult], with_ids=True, with_dates=True, metadata=None):
    #     vector_store = self.rag_documents.vector_store
        
    #     recs = await vector_store.add_documents(
    #             vectors=[a.vector for a in assets], 
    #             metadata=[self.asset_class(
    #                 # output=state.model_dump() if isinstance(state, BaseModel) else state,
    #                 # metadata=metadata.model_dump() if isinstance(metadata, BaseModel) else metadata,                    
    #                 output=a.output,
    #                 metadata=metadata or a.metadata,
    #                 asset_output_date=a.asset_output_date if with_dates else datetime.now(),
    #                 asset_update_ts=a.asset_update_ts if with_dates else get_int_timestamp()
    #             ) for a in assets], 
    #             ids=[a.id for a in assets] if with_ids else None,
    #             namespace=self.rag_documents.namespace
    #         )
    #     # return recs
    #     for r in recs:
    #         r.metadata = self.asset_class(
    #             id=r.id,
    #             input= r.metadata.get('input', None), 
    #             metadata=r.metadata.get('metadata', None), 
    #             output=r.metadata.get('output', None),
    #             asset_input_date=r.metadata.get('asset_input_date', None),
    #             asset_output_date=r.metadata['asset_output_date'],
    #             asset_update_ts=r.metadata['asset_update_ts']
    #         )
        
    #     return [self._pack_result(r) for r in recs]
    
    # async def get_asset(self, asset_id):
    #     assets = await self.get_assets(ids=[asset_id])
    #     if len(assets) == 0:
    #         return None
    #     return assets[0]

    # async def similar(self, input: BaseModel | str, partitions=None, top_k=10):
    #     partitions = partitions or {}
    #     partitions.update(self.partitions)
    #     output = await self.rag_documents.similarity(input, filters=partitions, top_k=top_k)
    #     return [self._pack_result(r) for r in output]
    #     # return self._pack_results(output)

    

    # async def delete_all(self):
    #     await self.rag_documents.delete_namespace()
    #     await self.rag_documents.verify_namespace()


    # def bind(self, metadata: BaseModel):
    #     self.curr_metadata = metadata
    #     return self
    


    # def to_dict(self):
    #     return self.dict()