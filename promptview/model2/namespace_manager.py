
from promptview.model2.base_namespace import DatabaseType, Namespace
from typing import TYPE_CHECKING, Type, TypeVar

from promptview.model2.postgres.namespace import PostgresNamespace


if TYPE_CHECKING:
    from promptview.model2.fields import Model



MODEL = TypeVar("MODEL", bound="Model")   

class NamespaceManager:
    # _instance: "NamespaceManager | None" = None
    _namespaces: dict[str, Namespace] = {}
    
    # def __new__(cls, *args, **kwargs):
    #     if cls._instance is None:
    #         cls._instance = super().__new__(cls)
    #     return cls._instance
    
    @classmethod
    def initialize(cls):
        cls._namespaces = {}
        
    @classmethod
    def build_namespace(cls, model_name: str, db_type: DatabaseType) -> Namespace:
        """
        Build a namespace for a model.
        """
        if not cls._namespaces:
            cls.initialize()
        if db_type == "qdrant":
            raise NotImplementedError("Qdrant is not implemented")
        elif db_type == "postgres":
            namespace = PostgresNamespace(model_name)            
        else:
           raise ValueError(f"Invalid database type: {db_type}")        
        cls._namespaces[model_name] = namespace
        return namespace
        
    
    @classmethod
    def get_namespace(cls, model_name: str) -> Namespace:
        if not cls._namespaces:
            raise ValueError("NamespaceManager not initialized")
        if not model_name in cls._namespaces:
            raise ValueError(f"Namespace for model {model_name} not found")
        return cls._namespaces[model_name]
    
    
    
