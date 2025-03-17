from promptview.model2.base_namespace import DatabaseType, Namespace
from typing import TYPE_CHECKING, Type, TypeVar, Dict, List, Any, Optional, ForwardRef

from promptview.model2.postgres.builder import SQLBuilder
from promptview.model2.postgres.namespace import PostgresNamespace
from promptview.model2.postgres.operations import PostgresOperations


if TYPE_CHECKING:
    from promptview.model2.model import Model
    from promptview.model2.versioning import Branch, Turn


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
    def build_namespace(cls, model_name: str, db_type: DatabaseType, is_versioned: bool = True, is_repo: bool = False, repo_namespace: Optional[str] = None) -> Namespace:
        """
        Build a namespace for a model.
        
        Args:
            model_name: The name of the model
            db_type: The type of database to use
            is_versioned: Whether the namespace should be versioned
            is_repo: Whether the namespace should be a repo
            repo_namespace: The namespace of the repo this model belongs to
            
        Returns:
            The namespace for the model
        """
        if not cls._namespaces:
            cls.initialize()
        if db_type == "qdrant":
            raise NotImplementedError("Qdrant is not implemented")
        elif db_type == "postgres":
            namespace = PostgresNamespace(model_name, is_versioned, is_repo, repo_namespace, namespace_manager=cls)
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
    async def create_all_namespaces(cls, partition_table: str, key: str = "id", versioning: bool = True):
        """
        Create all registered namespaces in the database.
        
        This method should be called after all models have been registered.
        """
        if not cls._namespaces:
            raise ValueError("No namespaces registered")
        if versioning:
            await SQLBuilder.initialize_versioning()
        for namespace in cls._namespaces.values():
            await namespace.create_namespace()
        
        if versioning:
            await SQLBuilder.add_partition_id_to_turns(partition_table, key)
        
        try:
            main_branch = await PostgresOperations.get_branch(1)
        except ValueError as e:        
            await PostgresOperations.create_branch(name="main")
        
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


    @classmethod
    async def create_turn(cls, partition_id: int, branch_id: int) -> "Turn":
        """
        Create a turn for a partition.
        """
        return await PostgresOperations.create_turn(partition_id, branch_id)
    
    @classmethod
    async def get_turn(cls, turn_id: int) -> "Turn":
        """
        Get a turn by id.
        """
        return await PostgresOperations.get_turn(turn_id)
    
    @classmethod
    async def create_branch(cls, name: Optional[str] = None, forked_from_turn_id: Optional[int] = None) -> "Branch":
        """
        Create a branch.
        """
        return await PostgresOperations.create_branch(name, forked_from_turn_id)
    
    @classmethod
    async def get_branch(cls, branch_id: int, raise_error: bool = False) -> "Branch | None":
        """
        Get a branch by id.
        """
        if raise_error:
            return await PostgresOperations.get_branch(branch_id)
        else:
            return await PostgresOperations.get_branch_or_none(branch_id)
    
    @classmethod
    async def commit_turn(cls, turn_id: int, message: Optional[str] = None) -> "Turn":
        """
        Commit a turn.
        """
        return await PostgresOperations.commit_turn(turn_id, message)
    
    
    
    