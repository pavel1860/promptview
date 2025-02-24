import asyncio
import inspect
import copy
import json
from typing import Any, Callable, Dict, ForwardRef, List, Optional, Self, Type, TypeVar,  get_args, get_origin
from uuid import uuid4
from pydantic import PrivateAttr, create_model, ConfigDict, BaseModel, Field
from pydantic.fields import FieldInfo
from pydantic._internal._model_construction import ModelMetaclass
from pydantic._internal._config import ConfigWrapper

from promptview.artifact_log.artifact_log3 import ArtifactLog
from promptview.model.head_model import HeadModel
from promptview.model.postgres_client import camel_to_snake
from .query import AllVecs, ModelFilterProxy, QueryFilter, ALL_VECS, QueryProxy, QuerySet, FusionType, QuerySetSingleAdapter, QueryType
from .vectors.base_vectorizer import BaseVectorizer
from .fields import VectorSpaceMetrics, get_model_indices
from .resource_manager import VectorSpace, connection_manager, DatabaseType

def unpack_list_model(pydantic_model):
    return get_args(pydantic_model)[0]




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
        return await self.cls.get_assets(top_k=1, filters=partitions, ascending=True)
        

    async def last(self, partitions=None):
        partitions = partitions or {}
        return await self.cls.get_assets(top_k=1, filters=partitions, ascending=False)
        





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
        db_type = "qdrant"
        versioned = False
        is_head = False
        vec_field_map = {}
        vector_spaces = []
        relations = {}
        is_abstract = False
        config = None
        if name == "Model":
            is_abstract = True
        
        
        if "Config" in dct:
            config = dct["Config"]
            if hasattr(config, "is_abstract"):
                is_abstract = config.is_abstract
        # extract config from base class
        elif bases and type(bases) == tuple and hasattr(bases[0], "Config"):
            config = bases[0].Config            
            
        if config:        
            if hasattr(config, "database_type"):
                db_type = config.database_type             
            if hasattr(config, "versioned"):
                versioned = config.versioned
            if hasattr(config, "is_head"):
                is_head = config.is_head 
            if hasattr(config, "namespace"):
                namespace = config.namespace
        for base in bases:
            if base == HeadModel:
                is_head = True
        
        
            
        
            
        
        if not is_abstract:
            #? add model partition
            if not bases:
                raise ValueError(f"Vector Space not defined in {name} and no base class")
            model_base = bases[0]
            if not namespace:
                if model_base == Model:
                    namespace = f"{camel_to_snake(name)}s" if db_type == "postgres" else name
                    dct["_subspace"] = None
                else:
                    if not hasattr(model_base, "_namespace"):
                        raise ValueError(f"Namespace not defined in base class of {name}")
                    namespace = model_base._namespace.default
                    dct["_subspace"] = name
            else:
                dct["_subspace"] = None
            # Get database type from Config class if it exists
            # if "Config" in dct:
            #     if hasattr(dct["Config"], "database_type"):
            #         db_type = dct["Config"].database_type             
            #     if hasattr(dct["Config"], "versioned"):
            #         versioned = dct["Config"].versioned
            #     if hasattr(dct["Config"], "is_head"):
            #         is_head = dct["Config"].is_head
            
            
            
            if "VectorSpace" in dct:
                field_type = dct["VectorSpace"]
                if not inspect.isclass(field_type.__class__):
                    raise ValueError(f"VectorSpace must be a class")
                #? vector space extraction
                vectorizers = field_type.__annotations__
                for vec_name, vec_cls in vectorizers.items():
                    vector_spaces.append(
                        VectorSpace(
                            name=vec_name,
                            namespace=namespace,
                            vectorizer_cls=vec_cls,
                            metric=VectorSpaceMetrics.COSINE                                
                        ))
                #? namespace and indices extraction
                indices = get_model_indices(dct)
                connection_manager.add_namespace(
                    namespace=namespace,
                    # subspace=dct.get("_subspace"),
                    vector_spaces=vector_spaces,
                    indices=indices,
                    db_type=db_type,
                    versioned=versioned,
                    is_head=is_head
                )
            else:
                if db_type == "qdrant":                    
                    ns = connection_manager.get_namespace2(namespace)                
                    if not ns:
                        raise ValueError("Vector Space not defined for Qdrant database")
                    vector_spaces = list(ns.vector_spaces.values())
                elif db_type == "postgres":
                    
                    indices = get_model_indices(dct)
                    connection_manager.add_namespace(
                        namespace=namespace,
                        vector_spaces=[],
                        indices=indices,
                        db_type=db_type,
                        versioned=versioned,
                        is_head=is_head
                    )
                else:
                    raise ValueError(f"Unsupported database type: {db_type}")
            # for field, field_type in dct.items():
            #     if inspect.isclass(field_type.__class__) and field == "VectorSpace":    
            #         #? vector space extraction
            #         vectorizers = field_type.__annotations__
            #         for vec_name, vec_cls in vectorizers.items():
            #             vector_spaces.append(
            #                 VectorSpace(
            #                     name=vec_name,
            #                     namespace=namespace,
            #                     vectorizer_cls=vec_cls,
            #                     metric=VectorSpaceMetrics.COSINE                                
            #                 ))
            #         #? namespace and indices extraction
            #         indices = get_model_indices(dct)
            #         connection_manager.add_namespace(
            #             namespace=namespace,
            #             # subspace=dct.get("_subspace"),
            #             vector_spaces=vector_spaces,
            #             indices=indices,
            #             db_type=db_type
            #         )
            #         break
            # else:
            #     ns = connection_manager.get_namespace2(namespace)
            #     vector_spaces = list(ns.vector_spaces.values())
            
            for field, field_type in dct.items():
                #? temporal field extraction
                if inspect.isclass(field_type.__class__):
                    # if isinstance(field_type, FieldInfo) and field_type.json_schema_extra:
                    #     if field_type.json_schema_extra.get("auto_now_add", None):
                    #         default_temporal_field = field
                    #         default_temporal_type = field_type                    
                    
                    # #? vector field extraction. the vector has to be a field of type VectorSpace
                    # if type(field_type) == FieldInfo:
                    #     if not field_type.json_schema_extra:
                    #         raise ValueError(f"You should use ModelField instead of pydantic Field for {field}")
                    #     if vec:= field_type.json_schema_extra.get("vec"):                            
                    #         for v in vec: # type: ignore
                    #             if v not in vec_field_map:
                    #                 vec_field_map[v] = []
                    #             vec_field_map[v] += [field]
                    if isinstance(field_type, FieldInfo):
                        if not field_type.json_schema_extra:
                            raise ValueError(f"You should use ModelField instead of pydantic Field for {field}")
                        if field_type.json_schema_extra.get("auto_now_add", None):
                            default_temporal_field = field
                            default_temporal_type = field_type                    
                    #? vector field extraction. the vector has to be a field of type VectorSpace
                        if vec:= field_type.json_schema_extra.get("vec"):                            
                            for v in vec: # type: ignore
                                if v not in vec_field_map:
                                    vec_field_map[v] = []
                                vec_field_map[v] += [field]
                        # if field_type.json_schema_extra.get("type", None) == "relation":
                        #     to_model_namespace = field_type.json_schema_extra.get("model", None)._namespace.default
                        #     key = field_type.json_schema_extra.get("key", None)
                        #     if not key:
                        #         raise ValueError(f"Relation key not defined for {field}")
                        #     connection_manager.add_relation(namespace, to_model_namespace, key)
                                
                    
                        #TODO validate that the vector exists in the vector space
            if vec_field_map:
                for vs in vector_spaces:
                    if vs.name not in vec_field_map:
                        raise ValueError(f"Vector Space '{vs.name}' not defined in model fields. if you are using explicit vector field mapping, ensure that all vectorizers are defined in the model fields")

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
                    if inspect.isclass(target_type) and issubclass(target_type, Model) or isinstance(target_type, ForwardRef): 
                            field_info = dct.get(field)                            
                            if not field_info:
                                raise ValueError(f"Field {field} is not defined")
                            partition = field_info.json_schema_extra.get("partition")
                            if not partition:
                                raise ValueError(f"Model Field {field} does not have partition")
                            _target_type, _forward_ref = (target_type, None) if not isinstance(target_type, ForwardRef) else (None, target_type)
                            cls_partitions[field] = {
                                "type": _target_type,
                                "origin": field_origin,
                                "partition": partition,
                                "field": field,
                                "forward_ref": _forward_ref,
                                "source_namespace": namespace,
                                "target_namespace": target_type._namespace.default
                            }
                            connection_manager.add_relation(target_type, cls_partitions[field])
                            # if field_type.json_schema_extra.get("type", None) == "relation":
                            # to_model_namespace = field_type.json_schema_extra.get("model", None)._namespace.default                            
                            # connection_manager.add_relation(namespace, field_type._namespace.default, partition)
                            field_info.default_factory = lambda: Relation(target_type, partition)
                            print("Found",field, partition)
                
            dct["_partitions"] = cls_partitions
            dct["_default_temporal_field"] = default_temporal_field
            dct["_vec_field_map"] = vec_field_map
            dct["_db_type"] = db_type
            if namespace:
                dct["_namespace"] = namespace
            # dct["_vectorizers"] = connection_manager.get_vectorizers(namespace)
        model_cls_inst = super().__new__(cls, name, bases, dct)
        if not is_abstract:
            if not namespace:
                raise ValueError("Namespace not defined")
            connection_manager.add_model(model_cls_inst)
            model_manager.add_asset(model_cls_inst)# type: ignore
        return model_cls_inst
    
    
    # def __getattr__(cls, name):
    #     if field_info:= cls.model_fields.get(name, None):
    #         # print("Getting attribute",cls.__name__, name)
    #         return FieldComparable(name, field_info)
    #     return super().__getattr__(name)





class Model(BaseModel, metaclass=ModelMeta):
    # _id: str = PrivateAttr(default_factory=lambda: str(uuid4()))
    # _score: float = PrivateAttr(default=-1)
    # id: str | int = Field(default_factory=lambda: str(uuid4()), description="Unique Identifier")
    id: str | int = Field(..., description="Unique Identifier")
    score: float = Field(default=-1, description="Score of the document. Default is -1")
    turn_id: str | int = Field(default=-1, description="Unique Identifier of the turn")
    branch_id: str | int = Field(default=-1, description="Unique Identifier of the branch")
    # head_id: str | int = Field(default=-1, description="Unique Identifier of the head")
    _partitions: dict[str, str] = PrivateAttr(default_factory=dict)
    _default_temporal_field: str = PrivateAttr(default=None)
    _namespace: str | None = PrivateAttr(default=None)
    _subspace: str | None = PrivateAttr(default=None)
    _vec_field_map: dict[str, list[str]] = PrivateAttr(default_factory=dict)
    _vector: dict[str, Any] = PrivateAttr(default_factory=dict)
    _db_type: DatabaseType = PrivateAttr(default="qdrant")
    # _partitions: dict[str, str] = {}
    # _default_temporal_field: str | None = None
    # _namespace: str | None = None
    # _subspace: str | None = None
    # _vec_field_map: dict[str, list[str]] = {}
    
    # class Config:
    #     arbitrary_types_allowed = True
    #     database_type: DatabaseType = "qdrant"  # Default to qdrant for backward compatibility
    #     versioned: bool = False
    #     is_head: bool = False
    
    
    def __init__(
            self,
            # _id=None, 
            # _score=None,
            _vector=None,
            **data
        ):
        if "id" not in data:
            if self.__class__.Config.database_type == "qdrant":
                data["id"] = str(uuid4())
            else:
                data["id"] = -1
        super().__init__(**data)
        # if _id:
        #     self._id = _id
        # if _score:
        #     self._score = _score 
        # if id:
        #     self.id = id
        if _vector:
            self._vector = _vector
        
        
    # @property
    # def id(self):
    #     return self._id
    
    # @property
    # def score(self):
    #     return self._score
    
    @property
    def vector(self):
        return self._vector
    
    
    
    @classmethod
    async def get_client(cls: Type["Model"]):
        if not cls._namespace:
            raise ValueError("Namespace not defined")
        ns = await connection_manager.get_namespace(cls._namespace)
        return ns.conn
        
    
    def _payload_dump(self):
        relation_fields = self._get_relation_fields()
        version_fields = ["turn_id", "branch_id", "main_branch_id", "head_id"]
            
            
        dump = self.model_dump(exclude={"id", "score", "_vector", *relation_fields, *version_fields})
        dump["_subspace"] = self._subspace
        return dump
        
    # async def verify_namespace(self):
        # await self.rag_documents.verify_namespace()
    def _get_relation_fields(self):
        if not self.__class__._partitions:
            return []
        return list(self.__class__._partitions.default.keys())
    
    @classmethod
    async def get_namespace(cls):
        if not cls._namespace:
            raise ValueError("Namespace not defined")
        namespace = cls._namespace.default # type: ignore
        return await connection_manager.get_namespace(namespace)
    
    @classmethod
    def _get_vec_field_map(cls: Type[MODEL]):
        return cls._vec_field_map.default# type: ignore

    def model_chunk(self, vectorizers: dict[str, BaseVectorizer])-> dict[str, str]:
        relation_fields = self._get_relation_fields()
        if not self._get_vec_field_map():
            model_dump = self.model_dump_json(exclude=set(relation_fields))
            return {vec_name: model_dump for vec_name in vectorizers}
        vec_strings = {}
        for vec, fields in self._get_vec_field_map().items():
            fields_str = [getattr(self, field) for field in fields]            
            vec_strings[vec] = "\n".join([str(f) for f in fields_str])
        return vec_strings
    
    
    @classmethod 
    async def query_embed(cls: Type[MODEL], query: str, vec: list[str]):
        ns = await cls.get_namespace()                
        vectorizers = {name: vs.vectorizer for name, vs in  ns.vector_spaces.items() if name in vec}
        tasks = [vectorizer.embed_documents([query]) for _, vectorizer in vectorizers.items()]
        vector_list = await asyncio.gather(*tasks)
        return {vec_name: vec[0] for vec_name, vec in zip(vectorizers.keys(), vector_list)}
    
    
    @classmethod
    async def model_batch_embed(cls: Type[MODEL], objs: List[MODEL]):
        ns = await cls.get_namespace()
        vectorizers = {name: vs.vectorizer for name, vs in  ns.vector_spaces.items()}
        chunks = [obj.model_chunk(vectorizers=vectorizers) for obj in objs]
        vector_list = await asyncio.gather(*[
            vectorizer.embed_documents([c[vec_name] for c in chunks])
            for vec_name, vectorizer in vectorizers.items()
        ])
        vec_names = list(vectorizers.keys())
        embeddings = []
        for vecs in zip(*vector_list):
            embeddings.append({vec_names[i]: vec for i, vec in enumerate(vecs)})
        return embeddings
        
        
    async def save(self):
        if not self._namespace:
            raise ValueError("Namespace not defined")
        # namespace = await connection_manager.get_namespace(self._namespace)
        
        ns = await self.get_namespace()
        vectors = await self.__class__.model_batch_embed([self])
        metadata = self._payload_dump()
        res = await ns.conn.upsert(
                namespace=self._namespace,
                vectors=vectors,
                metadata=[metadata],
                # ids=[self._id]
                ids=[self.id],
                model_cls=self.__class__,
                is_versioned=ns.versioned,
                is_head=ns.is_head
            )
        if not res:
            raise ValueError("Failed to save model")
        if not res[0].get('id'):
            raise ValueError("No id returned from database")
        # for field, field_info in self.model_fields.items():
        self.id = res[0].get('id')
        # self.branch_id = res[0].get('branch_id', -1)
        # self.turn_id = res[0].get('turn_id', -1)
        # self.head_id = res[0].get('head_id', -1)
        if hasattr(self, "after_save") and callable(self.after_save):
            await self.after_save(**res[0])
        return self

        
    
    # async def delete(self):
    #     ns = await self.get_namespace()
    #     return await ns.conn.delete(ns.name, ids=[self._id])
    
    @classmethod
    async def batch_delete(cls: Type[MODEL], ids: List[str] | None = None, filters: Callable[[QueryProxy[MODEL]], QueryFilter] | None = None):
        ns = await cls.get_namespace()
        query_filter = None
        if filters:
            query_proxy = QueryProxy[MODEL](cls)
            query_filter = filters(query_proxy)
        return await ns.conn.delete(ns.name, ids=ids, filters=query_filter)
    
    @classmethod
    async def delete(cls: Type[MODEL], id: str):
        ns = await cls.get_namespace()
        return await ns.conn.delete(ns.name, ids=[id])
    
    
        
        
    @classmethod
    async def batch_upsert(cls: Type[MODEL], points: List[MODEL]):
        vectors = await cls.model_batch_embed(points)
        metadata = [point._payload_dump() for point in points]
        # ids = [point._id for point in points]        
        ids = [point.id for point in points]
        ns = await cls.get_namespace()
        res = await ns.conn.upsert(
            namespace=cls._namespace.default,# type: ignore
            vectors=vectors,
            metadata=metadata,
            ids=ids
        )
        return res
    
    
    @classmethod
    async def pack_search_result(cls: Type[MODEL], search_result) -> MODEL:
        db_type = cls._db_type.default # type: ignore
        if db_type == "qdrant":
            # result = cls(
            #     # _id=search_result.id,
            #     # _score=search_result.score if hasattr(search_result, "score") else -1,
            # id=search_result.id,
            # score=search_result.score if hasattr(search_result, "score") else -1,
            # _vector=search_result.vector if hasattr(search_result, "vector") else {},
            # **search_result.payload
            # )
            result_dict = {
                "id": search_result.id,
                "score": search_result.score if hasattr(search_result, "score") else -1,
                "vector": search_result.vector if hasattr(search_result, "vector") else {},
                **search_result.payload
            }
        elif db_type == "postgres":
            result_dict = {}
            for field, field_info in cls.model_fields.items():
                field_type = field_info.annotation
                field_value = search_result.get(field)
                if field_value:
                    if field_type == dict or (inspect.isclass(field_type) and issubclass(field_type, BaseModel)):
                        result_dict[field] = json.loads(field_value)
                    else:
                        result_dict[field] = field_value
        else:
            raise ValueError(f"Unsupported database type: {db_type}")
        if hasattr(cls, "after_load") and callable(cls.after_load):
            await cls.after_load(**result_dict)
        return cls(
                **result_dict
            )
        
    @classmethod
    def _get_default_temporal_field(cls):
        if cls._default_temporal_field.default is not None: # type: ignore
            return cls._default_temporal_field.default # type: ignore
        else:
            parent_field = cls.__bases__[0]._get_default_temporal_field()            
            return parent_field
    
    
    @classmethod
    async def get_assets(cls: Type[MODEL], limit: int=10, filters=None, start_from=None, offset=0, ascending=False, ids=None):
        sort_key = cls._get_default_temporal_field()
        if not sort_key:
            raise ValueError("Temporal Field not defined")
        order_by = {
            "key": sort_key,
            "direction": "asc" if ascending else "desc",
            "start_from": start_from
        }
        namespace = cls._namespace.default# type: ignore
        ns = await connection_manager.get_namespace(namespace)
        res = await ns.conn.scroll(
            collection_name=namespace,
            limit=limit,
            filters=filters,
            order_by=order_by,
            offset=offset,
            ids=ids,
            with_payload=True,
            with_vectors=True
        )
        # res = await rag_documents.get_documents(top_k=top_k, filters=filters, order_by=order_by, offset=offset, ids=ids, with_vectors=True)
        return [cls.pack_search_result(r) for r in res]
    
    @classmethod
    async def get(cls: Type[MODEL], id: str) -> MODEL | None:
        ns = await cls.get_namespace()
        res = await ns.conn.retrieve(
            namespace=ns.name,
            ids=[id]
        )
        if not res:
            return None
        return cls.pack_search_result(res[0])
    
    @classmethod
    async def get_many(cls: Type[MODEL], ids: List[str] | List[int]) -> List[MODEL]:
        ns = await cls.get_namespace()
        res = await ns.conn.retrieve(
            namespace=ns.name,
            ids=ids
        )
        return [cls.pack_search_result(r) for r in res]
    
    @classmethod
    def build_query(cls: Type[MODEL], query_type: QueryType, partitions: dict[str, str] | None = None) -> QuerySet[MODEL]:
        partitions = partitions or {}
        if cls._subspace:
            partitions["_subspace"] = cls._subspace.default# type: ignore
        return QuerySet(cls, query_type=query_type, partitions=partitions)
        
    
    @classmethod
    def similar(cls: Type[MODEL], query: str, threshold: float | None = None, vec: list[str] | str | AllVecs = ALL_VECS, partitions: dict[str, str] | None = None, fusion: FusionType="rff") -> QuerySet[MODEL]:
        return cls.build_query("vector").similar(query, threshold, vec)
        # return QuerySet(cls, query_type="vector").similar(query, vec)    
    
    # @classmethod
    # def filter(cls: Type[MODEL], filters: Callable[[Type[MODEL]], QueryFilter]):
    #     return QuerySet(cls, query_type="scroll").filter(filters)
    @classmethod
    # def filter(cls: Type[MODEL], filters: Callable[[QueryProxy[MODEL]], QueryFilter], partitions: dict[str, str] | None = None) -> QuerySet[MODEL]:
    def filter(cls: Type[MODEL], filters: Callable[[MODEL], bool], partitions: dict[str, str] | None = None) -> QuerySet[MODEL]:
        return cls.build_query("scroll", partitions).filter(filters)
        # return QuerySet(cls, query_type="scroll").filter(filters)
    
    @classmethod
    def fusion(cls: Type[MODEL], *args, type: FusionType="rff", partitions: dict[str, str] | None = None) -> QuerySet[MODEL]:
        return cls.build_query("vector", partitions).fusion(*args, type=type)
        # return QuerySet(cls, query_type="vector").fusion(*args, type=type)
    
    @classmethod
    def first(cls: Type[MODEL], partitions: dict[str, str] | None = None) -> QuerySetSingleAdapter[MODEL]:
        return cls.build_query("scroll", partitions).first()
        # return QuerySet(cls, query_type="scroll").first()
    
    @classmethod
    def last(cls: Type[MODEL], partitions: dict[str, str] | None = None)  -> QuerySetSingleAdapter[MODEL]:
        return cls.build_query("scroll", partitions).last()
        # return QuerySet(cls, query_type="scroll").last()

    
    # @classmethod
    # def all(cls: Type[MODEL], partitions: dict[str, str] | None = None):
        # return cls.build_query("scroll", partitions).all()
        # return QuerySet(cls, query_type="scroll").all()
        
    @classmethod
    def limit(cls: Type[MODEL], limit: int, partitions: dict[str, str] | None = None) -> QuerySet[MODEL]:
        return cls.build_query("scroll", partitions).limit(limit)
     
    
    @classmethod
    def partition(cls: Type[MODEL], partitions: dict[str, str]) -> QuerySet[MODEL]:
        return cls.build_query("scroll", partitions)
    
    
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
    async def create(cls: Type[MODEL], **kwargs: Any) -> MODEL:
        obj = await cls(**kwargs).save()
        return obj
    
    # @classmethod
    # async def update_payload(cls: Type[MODEL], id: str, update: dict):
    #     pass
        
    def copy(self, with_ids: bool = True):
        payload = self._payload_dump()
        if not with_ids:
            payload.pop("id")
        obj = self.__class__(**payload)
        if self._vector:
            obj._vector = copy.deepcopy(self._vector)
        
        return obj
    
    @classmethod
    async def batch_copy(cls: Type[MODEL], objs: List[MODEL]) -> List[MODEL]:
        new_objs = [obj.copy() for obj in objs]
        return await cls.batch_upsert(new_objs)
        
        
    
    @classmethod
    async def delete_namespace(cls):
        await connection_manager.delete_namespace(cls._namespace.default)# type: ignore
    
    
    
    async def get_head(self):        
        head = await ArtifactLog.get_head(self.head_id)
        return head
    
    
    
    