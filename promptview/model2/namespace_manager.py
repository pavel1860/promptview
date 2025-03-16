from promptview.model2.base_namespace import DatabaseType, Namespace
from typing import TYPE_CHECKING, Type, TypeVar, Dict, List, Any, Optional, ForwardRef

from promptview.model2.postgres.namespace import PostgresNamespace
from promptview.model2.postgres.operations import PostgresOperations


if TYPE_CHECKING:
    from promptview.model2.fields import Model


MODEL = TypeVar("MODEL", bound="Model")

class NamespaceManager:
    """Manager for namespaces"""
    _namespaces: dict[str, Namespace] = {}
    _relations: dict[str, dict[str, dict[str, Any]]] = {}
    
    @classmethod
    def initialize(cls):
        """Initialize the namespace manager"""
        cls._namespaces = {}
        cls._relations = {}
        
    @classmethod
    def build_namespace(cls, model_name: str, db_type: DatabaseType, is_versioned: bool = True) -> Namespace:
        """
        Build a namespace for a model.
        
        Args:
            model_name: The name of the model
            db_type: The type of database to use
            is_versioned: Whether the namespace should be versioned
            
        Returns:
            The namespace for the model
        """
        if not cls._namespaces:
            cls.initialize()
        if db_type == "qdrant":
            raise NotImplementedError("Qdrant is not implemented")
        elif db_type == "postgres":
            namespace = PostgresNamespace(model_name, is_versioned)
        else:
           raise ValueError(f"Invalid database type: {db_type}")
        cls._namespaces[model_name] = namespace
        return namespace
        
    @classmethod
    def get_namespace(cls, model_name: str) -> Namespace:
        """
        Get a namespace by model name.
        
        Args:
            model_name: The name of the model
            
        Returns:
            The namespace for the model
            
        Raises:
            ValueError: If the namespace manager is not initialized or the namespace is not found
        """
        if not cls._namespaces:
            raise ValueError("NamespaceManager not initialized")
        if not model_name in cls._namespaces:
            raise ValueError(f"Namespace for model {model_name} not found")
        return cls._namespaces[model_name]
    
    @classmethod
    async def create_all_namespaces(cls, versioning: bool = True):
        """
        Create all registered namespaces in the database.
        
        This method should be called after all models have been registered.
        """
        if not cls._namespaces:
            raise ValueError("No namespaces registered")
        if versioning:
            await PostgresOperations.initialize_versioning()
        for namespace in cls._namespaces.values():
            await namespace.create_namespace()
    @classmethod
    def get_all_namespaces(cls) -> List[Namespace]:
        """
        Get all registered namespaces.
        
        Returns:
            A list of all registered namespaces
        """
        return list(cls._namespaces.values())
    
    @classmethod
    def register_relation(
        cls,
        source_namespace: str,
        relation_name: str,
        target_namespace: Optional[str],
        target_forward_ref: Optional[ForwardRef] = None,
        key: str = "id",
        on_delete: str = "CASCADE",
        on_update: str = "CASCADE",
    ):
        """
        Register a relation between namespaces.
        
        Args:
            source_namespace: The namespace of the source model
            relation_name: The name of the relation
            target_namespace: The namespace of the target model
            target_forward_ref: The forward reference to the target model
            key: The name of the foreign key in the target model
            on_delete: The action to take when the referenced row is deleted
            on_update: The action to take when the referenced row is updated
        """
        if source_namespace not in cls._relations:
            cls._relations[source_namespace] = {}
        
        cls._relations[source_namespace][relation_name] = {
            "target_namespace": target_namespace,
            "target_forward_ref": target_forward_ref,
            "key": key,
            "on_delete": on_delete,
            "on_update": on_update,
        }
    
    @classmethod
    def get_relations(cls, namespace: str) -> Dict[str, Dict[str, Any]]:
        """
        Get all relations for a namespace.
        
        Args:
            namespace: The namespace to get relations for
            
        Returns:
            A dictionary of relation names to relation information
        """
        return cls._relations.get(namespace, {})



    