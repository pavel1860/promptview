
from typing import TYPE_CHECKING, Dict
from contextvars import ContextVar

if TYPE_CHECKING:
    from qdrant_client import QdrantClient



class ConnectionHandler:
    
    _conn_storage: ContextVar[Dict[str, "QdrantClient"]] = ContextVar(
        "_conn_storage", default={}
    )
    
    
    def _create_connection(self, conn_name: str) -> "QdrantClient":
        conn_name: str = QdrantClient(url=conn_name)
    
    
    def get(self, conn_name: str) -> "QdrantClient":
        # return self._conn_storage.get().get(conn_name)
        storage: Dict[str, "QdrantClient"] = self._conn_storage.get()
        try:
            return storage[conn_name]
        except KeyError:
            connection: "QdrantClient" = self._create_connection(conn_name)