
from __future__ import annotations
from typing import Any, Dict, List, Optional, Type, TypeVar, Generic, Union
from uuid import uuid4

from promptview import RagDocuments
from pydantic import create_model, ConfigDict, BaseModel, Field
from qdrant_client.http.exceptions import UnexpectedResponse
import grpc
from promptview.model.fields import VectorSpaceMetrics
# from promptview.model.namespace import NamespaceParams, VectorSpace
from promptview.model.qdrant_client import QdrantClient
from promptview.model.vectors.base_vectorizer import BaseVectorizer











class RagDocumentsMenager:
    
    _rag_documents: Dict[str, RagDocuments] = {}
    
    def __init__(self):
        self._rag_documents = {}
        
    async def get_rag_documents(self, metadata_model: Type[BaseModel]):
        try:
            return self._rag_documents[metadata_model.__name__]
        except KeyError:
            rag_documents = RagDocuments(
                metadata_model.__name__,
                metadata_class=metadata_model,
                # vectorizers=[EmptyVectorizer(size=1536) if self.input_class is None else TextVectorizer()],
                # vectorizers=[EmptyVectorizer(size=1536)],
            )
            self._rag_documents[metadata_model.__name__] = rag_documents
            await rag_documents.verify_namespace()
            return rag_documents









class VectorSpace:
    name: str
    vectorizer_cls: Type[BaseVectorizer]
    metric: VectorSpaceMetrics
    
    def __init__(self, name: str, vectorizer_cls: Type[BaseVectorizer], metric: VectorSpaceMetrics):
        self.name = name
        self.vectorizer_cls = vectorizer_cls
        self.metric = metric
    
    @property
    def vectorizer(self):
        return connection_manager.vectorizers_manager.get_vectorizer(self.name)

    
class NamespaceParams:
    name: str
    vector_spaces: dict[str, VectorSpace]
    conn: QdrantClient
    
    def __init__(self, name: str, vector_spaces: list[VectorSpace], connection: QdrantClient):
        self.name = name
        self.vector_spaces = {vs.name: vs for vs in vector_spaces}
        self.conn = connection

    def get(self, vector_space: str):
        return self.vector_spaces[vector_space]
    
        

class VectorizersManager:
    _vectorizers: Dict[str, BaseVectorizer]
    _named_vectorizers: Dict[str, BaseVectorizer] 
    
    def __init__(self):
        self._vectorizers = {}
        self._named_vectorizers = {}
        
    def get_vectorizer(self, vector_name: str) -> BaseVectorizer:
        try:
            return self._named_vectorizers[vector_name]
        except KeyError:
            raise ValueError(f"Vectorizer {vector_name} not found")
        
    def get_vectorizer_cls(self, vectorizer_model: Type[BaseModel])->BaseVectorizer:
        try:
            return self._vectorizers[vectorizer_model.__name__]
        except KeyError:
            raise ValueError(f"Vectorizer {vectorizer_model.__name__} not found")
        
    def add_vectorizer(self, vector_name: str, vectorizer_cls: Type[BaseVectorizer]) -> BaseVectorizer:
        if not vectorizer_cls.__name__ in self._vectorizers:
            self._vectorizers[vectorizer_cls.__name__] = vectorizer_cls()        
        vectorizer = self._vectorizers[vectorizer_cls.__name__]
        self._named_vectorizers[vector_name] = vectorizer
        return vectorizer


    
        
class ConnectionManager:
    
    # _vector_db_connections: Dict[str, Any] = {}
    _qdrant_connection: QdrantClient 
    _namespaces: Dict[str, NamespaceParams] = {}
    _active_namespaces: Dict[str, NamespaceParams] = {}
    
    def __init__(self):        
        self._qdrant_connection = QdrantClient()
        self._namespaces = {}
        self.vectorizers_manager = VectorizersManager()
        # self._vector_db_connections = {}
        
    # async def get_connection(self, db_name: str):
    #     try:
    #         return self._db_connections[db_name]
    #     except KeyError:
    #         raise ValueError(f"Connection {db_name} not found")
    
    
    def get_vec_db_conn(self, db_name: str):
        try:
            return self._qdrant_connection
        except KeyError:
            raise ValueError(f"Connection {db_name} not found")
                
    def add_namespace(self, namespace: str, vector_spaces: list[VectorSpace]):        
        self._namespaces[namespace] = NamespaceParams(
            name=namespace,
            vector_spaces=vector_spaces,
            connection=self._qdrant_connection
        )
        for vs in vector_spaces:
            self.vectorizers_manager.add_vectorizer(vs.name, vs.vectorizer_cls)
        return self._namespaces[namespace]
        
    async def get_vectorizers(self, namespace: str):
        try:
            namespace_inst = self._namespaces[namespace]
            return {
                vs.name: self.vectorizers_manager.get_vectorizer(vs.vectorizer.__name__) 
                for vs in namespace_inst.vector_spaces
            }
        except KeyError:
            raise ValueError(f"Namespace {namespace} not found")
        
    async def get_namespace(self, namespace: str)->NamespaceParams:
        try:
            ns = self._active_namespaces[namespace]
            # vectorizers = {vs.name: self.vectorizers_manager.get_vectorizer(vs.vectorizer.__name__)
            #     for vs in namespace_inst.vector_spaces}            
            return ns
        except KeyError:
            try:
                ns = self._namespaces[namespace]                
                create_result = await ns.conn.create_collection(
                    collection_name=namespace,
                    vector_spaces=list(ns.vector_spaces.values())
                )
                if not create_result:
                    raise ValueError(f"Some error occured while creating collection {namespace}")
                self._active_namespaces[namespace] = ns
                return ns
            except KeyError:
                raise ValueError(f"Collection {namespace} not found")
        
        
    async def validate_namespace(self):
        try:
            await self.vector_store.info()
        except (UnexpectedResponse, grpc.aio._call.AioRpcError) as e:            
            await self.create_namespace()

        




        

# connection_manager = RagDocumentsMenager()
connection_manager = ConnectionManager()









# from typing import TYPE_CHECKING, Dict
# from contextvars import ContextVar

# if TYPE_CHECKING:
#     from qdrant_client import QdrantClient

# class ConnectionHandler:
    
#     _conn_storage: ContextVar[Dict[str, "QdrantClient"]] = ContextVar(
#         "_conn_storage", default={}
#     )
    
    
#     def _create_connection(self, conn_name: str) -> "QdrantClient":
#         conn_name: str = QdrantClient(url=conn_name)
    
    
#     def get(self, conn_name: str) -> "QdrantClient":
#         # return self._conn_storage.get().get(conn_name)
#         storage: Dict[str, "QdrantClient"] = self._conn_storage.get()
#         try:
#             return storage[conn_name]
#         except KeyError:
#             connection: "QdrantClient" = self._create_connection(conn_name)
