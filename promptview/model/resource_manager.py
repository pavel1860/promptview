from __future__ import annotations
import contextlib
import os
from typing import Any, Dict, List, Optional, Type, TypeVar, Generic, Union, TYPE_CHECKING, Literal
from uuid import uuid4
from pydantic import BaseModel
from qdrant_client.http.exceptions import UnexpectedResponse
import grpc
from contextvars import ContextVar

# from promptview.artifact_log.artifact_log2 import BaseArtifact, create_artifact_table_for_model

from .fields import VectorSpaceMetrics
from .qdrant_client import QdrantClient
from .postgres_client import PostgresClient
from .vectors.base_vectorizer import BaseVectorizer
if TYPE_CHECKING:
    from promptview.model.model import Model

DatabaseType = Literal["qdrant", "postgres"]

def get_qdrant_connection():
    if not os.environ.get("QDRANT_URL"):
        return None
    return QdrantClient(
        url=os.environ.get("QDRANT_URL"),
        api_key=os.environ.get("QDRANT_API_KEY", None)
    )

def get_postgres_connection():
    if not os.environ.get("POSTGRES_URL"):
        return None
    return PostgresClient(
        url=os.environ.get("POSTGRES_URL"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
        database=os.environ.get("POSTGRES_DB", "postgres"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432"))
    )

class VectorSpace:
    name: str
    namespace: str
    vectorizer_cls: Type[BaseVectorizer]
    metric: VectorSpaceMetrics
    
    def __init__(self, namespace: str, name: str, vectorizer_cls: Type[BaseVectorizer], metric: VectorSpaceMetrics):
        self.name = name
        self.namespace = namespace
        self.vectorizer_cls = vectorizer_cls
        self.metric = metric
    
    @property
    def vectorizer(self):
        return connection_manager.vectorizers_manager.get_vectorizer(self.namespace, self.name)

class NamespaceParams:
    _name: str
    subspaces: list[str]
    vector_spaces: dict[str, VectorSpace]
    conn: QdrantClient | PostgresClient
    indices: list[dict[str, str]]
    envs: dict[str, dict[str, str]]
    db_type: DatabaseType
    is_head: bool
    versioned: bool
    
    def __init__(
            self, 
            name: str, 
            envs: dict[str, dict[str, str]],
            vector_spaces: list[VectorSpace], 
            connection: QdrantClient | PostgresClient,
            db_type: DatabaseType,
            indices: list[dict[str, str]] | None = None,
            subspaces: list[str] | None = None,
            versioned: bool = False,
            is_head: bool = False,
        ):
        self._name = name
        self.vector_spaces = {vs.name: vs for vs in vector_spaces}
        self.conn = connection
        self.indices = indices or []
        self.subspaces = subspaces or []
        self.envs = envs
        self.db_type = db_type
        self.versioned = versioned
        self.is_head = is_head
        
    @property
    def name(self):
        return self.envs[ENV_CONTEXT.get()][self._name]

    def get(self, vector_space: str):
        return self.vector_spaces[vector_space]
    
    def add_subspace(self, subspace: str, indices: list[dict[str, str]]):
        if subspace in self.subspaces:
            raise ValueError(f"Subspace {subspace} already exists")
        self.subspaces.append(subspace)
        new_idx_field_set = set([idx["field"] for idx in indices])
        for idx in self.indices:
            if idx["field"] in new_idx_field_set:
                raise ValueError(f"Index {idx['field']} already exists")            
        self.indices += indices

class VectorizersManager:
    _vectorizers: Dict[str, BaseVectorizer]
    _named_vectorizers: Dict[str, BaseVectorizer] 
    
    def __init__(self):
        self._vectorizers = {}
        self._named_vectorizers = {}
        
    def get_vectorizer(self, namespace: str, vector_name: str) -> BaseVectorizer:
        name = f"{namespace}_{vector_name}"
        try:
            return self._named_vectorizers[name]
        except KeyError:
            raise ValueError(f"Vectorizer {vector_name} not found")
        
    def get_vectorizer_cls(self, vectorizer_model: Type[BaseModel])->BaseVectorizer:
        try:
            return self._vectorizers[vectorizer_model.__name__]
        except KeyError:
            raise ValueError(f"Vectorizer {vectorizer_model.__name__} not found")
        
    def add_vectorizer(self, namespace: str, vector_name: str, vectorizer_cls: Type[BaseVectorizer]) -> BaseVectorizer:
        name = f"{namespace}_{vector_name}"
        if not vectorizer_cls.__name__ in self._vectorizers:
            self._vectorizers[vectorizer_cls.__name__] = vectorizer_cls() # type: ignore
        vectorizer = self._vectorizers[vectorizer_cls.__name__]
        self._named_vectorizers[name] = vectorizer
        return vectorizer
    
    
# class ArtifactRegistry:
#     _artifacts: Dict[str, type]
    
#     def __init__(self):
#         self._artifacts = {}
                
#     def create_artifact_table(self, model_cls: Type[Model]):
#         artifact_cls = create_artifact_table_for_model(model_cls)
#         self._artifacts[model_cls.__name__] = artifact_cls
#         return artifact_cls
        
        

ENV_CONTEXT = ContextVar("ENV_CONTEXT", default="default")

class ConnectionManager:
    _qdrant_connection: QdrantClient 
    _postgres_connection: PostgresClient
    _namespaces: Dict[str, NamespaceParams] = {}
    _active_namespaces: Dict[str, NamespaceParams] = {}
    _models: Dict[str, Type[Model]] = {}
    
    def __init__(self):        
        self._qdrant_connection = get_qdrant_connection()
        self._postgres_connection = get_postgres_connection()
        self._namespaces = {}
        self.vectorizers_manager = VectorizersManager()
        self._envs = {"default": {}}
    
    def get_connection(self, db_type: DatabaseType):
        if db_type == "qdrant":
            return self._qdrant_connection
        elif db_type == "postgres":
            return self._postgres_connection
        else:
            raise ValueError(f"Unknown database type: {db_type}")
                
    def add_namespace(
        self, 
        namespace: str, 
        vector_spaces: list[VectorSpace], 
        db_type: DatabaseType = "qdrant",
        indices: list[dict[str, str]] | None=None,
        versioned: bool = False,
        is_head: bool = False,
    ):        
        if namespace in self._namespaces:
            raise ValueError(f"Namespace {namespace} already exists. seems you have multiple Model classes with the same name")
        self._envs["default"][namespace] = namespace
        self._namespaces[namespace] = NamespaceParams(
            name=namespace,
            envs=self._envs,
            vector_spaces=vector_spaces,
            connection=self.get_connection(db_type),
            db_type=db_type,
            indices=indices or [],
            versioned=versioned,
            is_head=is_head,
        )        
        for vs in vector_spaces:
            self.vectorizers_manager.add_vectorizer(namespace, vs.name, vs.vectorizer_cls)
        return self._namespaces[namespace]
    
    def add_env(self, env_name: str, env: dict[str, str]):
        self._envs[env_name] = env
        
    def get_env_names(self):
        return list(self._envs.keys())
        
    @contextlib.contextmanager
    def set_env(self, env_name: str):
        token = ENV_CONTEXT.set(env_name)
        try:
            yield
        finally:
            ENV_CONTEXT.reset(token)
            
    def get_env(self):
        return ENV_CONTEXT.get()
    
    def add_model(self, model_cls: Type[Model]):
        self._models[model_cls._namespace.default] = model_cls # type: ignore
        
    def get_model(self, model_name: str) -> Type[Model]:
        try:
            return self._models[model_name]
        except KeyError:
            raise ValueError(f"Model {model_name} not found")
    
    def add_subspace(self, namespace: str, subspace: str, indices: list[dict[str, str]]):
        if namespace not in self._namespaces:
            raise ValueError(f"Namespace {namespace} not found while adding subspace {subspace}")
        self._namespaces[namespace].add_subspace(subspace, indices)
        
        
    async def _create_all_namespaces(self):
        sql = ""
        for ns in self._namespaces.values():            
            if ns.db_type == "postgres":
                sql += "\n" + ns.conn.build_table_sql(  # type: ignore
                    collection_name=ns.name,
                    model_cls=self.get_model(ns.name),
                    vector_spaces=list(ns.vector_spaces.values()),
                    indices=ns.indices,
                    versioned=ns.versioned,
                    is_head=ns.is_head,
                )
                self._active_namespaces[ns.name] = ns            
            else:
                await self._create_namespace(ns.name)                
        if sql:
            res = await self._postgres_connection.execute_sql(sql)
            print(res)
                
                
    async def _create_namespace(self, namespace: str):
        try:
            ns = self._namespaces[namespace]
            if ns.db_type == "qdrant":
                collection = await ns.conn.get_collection(namespace, raise_error=False)  # type: ignore
                if not collection:
                    subspace_index = []
                    if ns.subspaces:
                        subspace_index = [{"field": "_subspace", "schema": "keyword"}]
                    create_result = await ns.conn.create_collection(
                        collection_name=namespace,
                        model_cls=self.get_model(namespace),
                        vector_spaces=list(ns.vector_spaces.values()),
                        indices=ns.indices + subspace_index
                    )
                    if not create_result:
                        raise ValueError(f"Some error occured while creating collection {namespace}")
            elif ns.db_type == "postgres":
                await ns.conn.create_collection(  # type: ignore
                    collection_name=namespace,
                    model_cls=self.get_model(namespace),
                    vector_spaces=list(ns.vector_spaces.values()),
                    indices=ns.indices,
                    
                )
            self._active_namespaces[namespace] = ns
            return ns
        except KeyError:
            raise ValueError(f"Collection {namespace} not found")
    
    def get_namespace2(self, namespace: str):
        return self._namespaces.get(namespace, None)
        
    async def get_namespace(self, namespace: str)->NamespaceParams:
        try:
            ns = self._active_namespaces[namespace]          
            return ns
        except KeyError:
            await self._create_all_namespaces()
            return self._active_namespaces[namespace]
            # return await self._create_namespace(namespace)
    
    async def add_namespace_indices(self, namespace: str, indices: list[dict[str, str]]):
        ns = await self.get_namespace(namespace)
        ns.indices += indices        
        return ns    
        
    async def delete_namespace(self, namespace: str):
        try:
            ns = self._namespaces[namespace]
            if ns.db_type == "qdrant":
                await self._qdrant_connection.delete_collection(namespace)
            elif ns.db_type == "postgres":
                await self._postgres_connection.delete_collection(namespace)
            if namespace in self._active_namespaces:
                del self._active_namespaces[namespace]
            if namespace in self._namespaces:
                del self._namespaces[namespace]            
        except (UnexpectedResponse, grpc.aio._call.AioRpcError) as e:
            pass
        
    def reset_connection(self):
        self._qdrant_connection = get_qdrant_connection()
        self._postgres_connection = get_postgres_connection()
        
    async def init_all_namespaces(self):
        await self._create_all_namespaces()

connection_manager = ConnectionManager()




