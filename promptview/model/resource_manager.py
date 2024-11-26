
from __future__ import annotations
import os
from typing import Any, Dict, List, Optional, Type, TypeVar, Generic, Union
from uuid import uuid4
from pydantic import BaseModel
from qdrant_client.http.exceptions import UnexpectedResponse
import grpc
from .fields import VectorSpaceMetrics
from .qdrant_client import QdrantClient
from .vectors.base_vectorizer import BaseVectorizer





def get_qdrant_connection():
    return QdrantClient(
        url = os.environ.get("QDRANT_URL"),
        api_key =os.environ.get("QDRANT_API_KEY", None)
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
    name: str
    subspaces: list[str]
    vector_spaces: dict[str, VectorSpace]
    conn: QdrantClient
    indices: list[dict[str, str]]
    
    def __init__(
            self, 
            name: str, 
            vector_spaces: list[VectorSpace], 
            connection: QdrantClient, 
            indices: list[dict[str, str]] | None = None,
            subspaces: list[str] | None = None
        ):
        self.name = name
        self.vector_spaces = {vs.name: vs for vs in vector_spaces}
        self.conn = connection
        self.indices = indices or []
        self.subspaces = subspaces or []

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


    
        
class ConnectionManager:
    
    # _vector_db_connections: Dict[str, Any] = {}
    _qdrant_connection: QdrantClient 
    _namespaces: Dict[str, NamespaceParams] = {}
    _active_namespaces: Dict[str, NamespaceParams] = {}
    
    def __init__(self):        
        self._qdrant_connection = get_qdrant_connection()
        self._namespaces = {}
        self.vectorizers_manager = VectorizersManager()
        # self._vector_db_connections = {}
        
    
    
    
    def get_vec_db_conn(self, db_name: str):
        try:
            return self._qdrant_connection
        except KeyError:
            raise ValueError(f"Connection {db_name} not found")
                
    def add_namespace(self, namespace: str, vector_spaces: list[VectorSpace], indices: list[dict[str, str]] | None=None):        
        self._namespaces[namespace] = NamespaceParams(
            name=namespace,
            vector_spaces=vector_spaces,
            connection=self._qdrant_connection,
            indices=indices or []
        )
        for vs in vector_spaces:
            self.vectorizers_manager.add_vectorizer(namespace, vs.name, vs.vectorizer_cls)
        return self._namespaces[namespace]
    
    def add_subspace(self, namespace: str, subspace: str, indices: list[dict[str, str]]):
        if namespace not in self._namespaces:
            raise ValueError(f"Namespace {namespace} not found while adding subspace {subspace}")
        self._namespaces[namespace].add_subspace(subspace, indices)
        
    # async def get_vectorizers(self, namespace: str):
    #     try:
    #         namespace_inst = self._namespaces[namespace]
    #         return {
    #             vs.name: self.vectorizers_manager.get_vectorizer(vs.vectorizer.__name__) 
    #             for vs in namespace_inst.vector_spaces.values()
    #         }
    #     except KeyError:
    #         raise ValueError(f"Namespace {namespace} not found")
        
    async def _create_namespace(self, namespace: str):
        try:
            ns = self._namespaces[namespace]
            collection = await ns.conn.get_collection(namespace, raise_error=False)
            if not collection:
                subspace_index = []
                if ns.subspaces:
                    subspace_index = [{"field": "_subspace", "schema": "keyword"}]
                create_result = await ns.conn.create_collection(
                    collection_name=namespace,
                    vector_spaces=list(ns.vector_spaces.values()),
                    indices=ns.indices + subspace_index
                )
                if not create_result:
                    raise ValueError(f"Some error occured while creating collection {namespace}")
            self._active_namespaces[namespace] = ns
            return ns
        except KeyError:
            raise ValueError(f"Collection {namespace} not found")
    
    def get_namespace2(self, namespace: str):
        try:
            ns = self._namespaces[namespace]
            return ns
        except KeyError:
            raise ValueError(f"Namespace {namespace} not found")
        
        
    async def get_namespace(self, namespace: str)->NamespaceParams:
        try:
            ns = self._active_namespaces[namespace]          
            return ns
        except KeyError:
            return await self._create_namespace(namespace)
    
    async def add_namespace_indices(self, namespace: str, indices: list[dict[str, str]]):
        ns = await self.get_namespace(namespace)
        ns.indices += indices        
        return ns    
        
            
    async def delete_namespace(self, namespace: str):
        try:
            await self._qdrant_connection.delete_collection(namespace)
            if namespace in self._active_namespaces:
                del self._active_namespaces[namespace]
            if namespace in self._namespaces:
                del self._namespaces[namespace]            
        except (UnexpectedResponse, grpc.aio._call.AioRpcError) as e:
            pass

        
    def reset_connection(self):
        self._qdrant_connection = get_qdrant_connection()
        
        



        


connection_manager = ConnectionManager()




