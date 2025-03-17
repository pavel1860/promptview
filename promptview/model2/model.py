from typing import Any, Dict, Generic, Optional, Type, TypeVar, Callable, cast, ForwardRef, get_args, get_origin
from pydantic import BaseModel, Field, PrivateAttr
from pydantic.config import JsonDict
from pydantic._internal._model_construction import ModelMetaclass
from pydantic.fields import FieldInfo
import pydantic_core

from promptview.model2.context import Context
from promptview.model2.namespace_manager import NamespaceManager
from promptview.model2.base_namespace import DatabaseType
from promptview.model2.versioning import Branch, Turn
from promptview.model2.postgres.operations import PostgresOperations
from promptview.utils.string_utils import camel_to_snake

T = TypeVar('T', bound=BaseModel)



def get_dct_private_attributes(dct: dict[str, Any], key: str, default: Any=None) -> Any:
    """Get the private attributes of a class"""
    # res = dct['__private_attributes__'].get(key)
    res = dct.get(key)
    if res is not None and hasattr(res, "default"):
        res = res.default
    if not res:
        return default
    return res



def build_namespace(model_cls_name: str, db_type: DatabaseType = "postgres"):
    return f"{camel_to_snake(model_cls_name)}s" if db_type == "postgres" else model_cls_name


def parse_version_params(turn: Optional[int | Turn] = None, branch: Optional[int | Branch] = None) -> tuple[Optional[int], Optional[int]]:
    branch_id = None
    turn_id = None    
    ctx = Context.get_current(raise_error=False)    
    
    if branch:
        if isinstance(branch, int):
            branch_id = branch
        elif isinstance(branch, Branch):
            branch_id = branch.id
    else:
        if ctx:
            branch_id = ctx.branch.id
        else:
            branch_id = 1
    if not turn:
        if ctx:
            turn_id = ctx.turn.id
        else:
            raise ValueError("Turn is not provided")
    elif isinstance(turn, Turn):
        turn_id = turn.id
    else:
        turn_id = turn
    return turn_id, branch_id
            
class ModelMeta(ModelMetaclass, type):
    """Metaclass for Model
    
    This metaclass handles the registration of models with the namespace manager
    and the processing of fields.
    """
    
    def __new__(cls, name, bases, dct):
        # Use the standard Pydantic metaclass to create the class
        
        
        # Skip processing for the base Model class
        if name == "Model" or name == "RepoModel" or name == "ArtifactModel":
            cls_obj = super().__new__(cls, name, bases, dct)
            return cls_obj
        
        # Get model name and namespace
        model_name = name
        db_type = get_dct_private_attributes(dct, "_db_type", "postgres")
        namespace_name = get_dct_private_attributes(dct, "_namespace_name", build_namespace(model_name))        
        
        # Check if this is a repo model or an artifact model
        is_repo = len(bases) >= 1 and bases[0].__name__ == "RepoModel"
        
        
        # If _repo is specified, the model is automatically versioned
        is_versioned = get_dct_private_attributes(dct, "_is_versioned", False) or (len(bases) >= 1 and bases[0].__name__ == "ArtifactModel")
        repo_namespace = get_dct_private_attributes(dct, "_repo", "main" if is_versioned else None)
        if repo_namespace is None and is_versioned:
            raise ValueError("RepoModel must have a repo namespace")
        
        if is_repo and is_versioned:
            raise ValueError("RepoModel cannot be versioned")
        
        # Build namespace
        ns = NamespaceManager.build_namespace(namespace_name, db_type, is_versioned, is_repo, repo_namespace)
        # Process fields and relations
        relations = {}
        for field_name, field_info in dct.items():
            # Skip fields without a type annotation
            if not isinstance(field_info, FieldInfo):
                continue
            
            field_type = dct["__annotations__"].get(field_name)
            if field_type is None:
                continue
            
            # Extract field metadata
            extra_json = field_info.json_schema_extra
            extra: Dict[str, Any] = {}
            
            # Convert json_schema_extra to a dictionary
            if extra_json is not None:
                if isinstance(extra_json, dict):
                    extra = dict(extra_json)
                elif callable(extra_json):
                    # If it's a callable, create an empty dict
                    # In a real implementation, we might want to call it
                    extra = {}
            
            # Check if this is a relation field
            field_origin = get_origin(field_type)
            if field_origin and field_origin == Relation:
                # Get the model class from the relation
                target_type = get_relation_model(field_type)
                
                # Get the relation key
                key = extra.get("key")
                if not key:
                    continue
                
                # Create a relation blueprint
                relations[field_name] = {
                    "key": key,
                    "target_type": target_type,
                    "on_delete": extra.get("on_delete", "CASCADE"),
                    "on_update": extra.get("on_update", "CASCADE"),
                }
                
                # Set the default factory for the field
                field_info.default_factory = make_default_factory(target_type, key)
                
                # Skip adding this field to the namespace
                continue
            
            # Add field to namespace
            ns.add_field(field_name, field_type, extra)
        
        # Set namespace name and relations on the class
        cls_obj = super().__new__(cls, name, bases, dct)
        cls_obj._namespace_name = namespace_name
        cls_obj._relations = relations
        cls_obj._is_versioned = is_versioned
        
        # Register relations with the namespace manager
        for relation_name, relation_info in relations.items():
            target_type: Any = relation_info["target_type"]
            # If target_type is a ForwardRef, we need to resolve it later
            target_namespace = None
            if not isinstance(target_type, ForwardRef) and hasattr(target_type, "_namespace_name"):
                target_namespace = target_type._namespace_name
            
            # Get the key, on_delete, and on_update values
            key = relation_info.get("key", "id")
            on_delete = relation_info.get("on_delete", "CASCADE")
            on_update = relation_info.get("on_update", "CASCADE")
            # Register the relation
            NamespaceManager.register_relation(
                source_namespace=namespace_name,
                relation_name=relation_name,
                target_namespace=target_namespace,
                target_forward_ref=target_type if isinstance(target_type, ForwardRef) else None,
                key=key,
                on_delete=on_delete,
                on_update=on_update,
            )
        
        return cls_obj


class Model(BaseModel, metaclass=ModelMeta):
    """Base class for all models
    
    This class is a simple Pydantic model with a custom metaclass.
    The ORM functionality is added by the metaclass.
    """
    # Namespace reference - will be set by the metaclass
    _namespace_name: str = PrivateAttr(default=None)
    _db_type: DatabaseType = PrivateAttr(default="postgres")
    _is_versioned: bool = PrivateAttr(default=False)
    _relations: Dict[str, Dict[str, Any]] = PrivateAttr(default_factory=dict)
    
    
    @classmethod
    def get_namespace_name(cls) -> str:
        """Get the namespace name for this model"""
        return cls._namespace_name
    
    @classmethod
    async def initialize(cls):
        """Initialize the model (create table)"""
        ns = NamespaceManager.get_namespace(cls.get_namespace_name())
        await ns.create_namespace()
    
    def _get_relation_fields(self):
        """Get the names of relation fields."""
        return list(self.__class__._relations.keys())
    
    def _update_relation_instance(self):
        """Update the instance for all relations."""
        # Get the ID from the model instance
        # The ID field should be defined by the user
        if not hasattr(self, "id"):
            return
        
        for field_name in self._get_relation_fields():
            relation = getattr(self, field_name)
            if relation:
                relation.set_instance(self)
                
    def model_dump(self, *args, **kwargs):
        relation_fields = self._get_relation_fields()
        exclude = kwargs.get("exclude", set())
        if not isinstance(exclude, set):
            exclude = set()
        exclude.update(relation_fields)
        kwargs["exclude"] = exclude
        res = super().model_dump(*args, **kwargs)
        return res
                
    def _payload_dump(self):
        relation_fields = self._get_relation_fields()
        version_fields = ["turn_id", "branch_id", "main_branch_id", "head_id"]
            
        dump = self.model_dump(exclude={"id", "score", "_vector", *relation_fields, *version_fields})
        return dump
    
    async def save(self, *args, **kwargs):
        """
        Save the model instance to the database
        """        
                
        ns = NamespaceManager.get_namespace(self.__class__.get_namespace_name())
        data = self._payload_dump()
        result = await ns.save(data)
        # Update instance with returned data (e.g., ID)
        for key, value in result.items():
            setattr(self, key, value)
        
        # Update relation instance IDs
        self._update_relation_instance()
        
        return self
    
    @classmethod
    async def get(cls, id: Any):
        """Get a model instance by ID"""
        ns = NamespaceManager.get_namespace(cls.get_namespace_name())
        data = await ns.get(id)
        if data is None:
            raise ValueError(f"Model with ID {id} not found")
        return cls(**data)
    
    @classmethod
    async def get_or_none(cls, id: Any):
        """Get a model instance by ID or None if it doesn't exist"""
        ns = NamespaceManager.get_namespace(cls.get_namespace_name())
        data = await ns.get(id)
        return cls(**data) if data else None
    
    @classmethod
    def query(cls, partition_id: Optional[int] = None, branch: Optional[int | Branch] = None):
        """
        Create a query for this model
        
        Args:
            branch: Optional branch ID to query from
        """
        if branch:
            if not cls._is_versioned:
                raise ValueError("Model is not versioned but branch is provided")
            if isinstance(branch, Branch):
                branch = branch.id
        else:
            if cls._is_versioned:
                branch = 1
            
        ns = NamespaceManager.get_namespace(cls.get_namespace_name())
        return ns.query(partition_id, branch, model_class=cls)


# No need for the ModelFactory class anymore




class ArtifactModel(Model):
    """
    A model that is versioned and belongs to a repo.
    """
    branch_id: int = Field(default=None)
    turn_id: int = Field(default=None)
    _repo: str = PrivateAttr(default=None)  # Namespace of the repo model
    
    
    async def save(self, turn: Optional[int | Turn], branch: Optional[int | Branch] = None):
        """
        Save the artifact model instance to the database
        
        Args:
            branch: Optional branch ID to save to
            turn: Optional turn ID to save to
        """        
        turn_id, branch_id = parse_version_params(turn, branch)
                
        ns = NamespaceManager.get_namespace(self.__class__.get_namespace_name())
        data = self._payload_dump()
        result = await ns.save(data, branch_id=branch_id, turn_id=turn_id)
        # Update instance with returned data (e.g., ID)
        for key, value in result.items():
            setattr(self, key, value)
        
        # Update relation instance IDs
        self._update_relation_instance()
        
        return self

    
    
    

class RepoModel(Model):
    """
    A model that represents a repository with branches and turns.
    """
    main_branch_id: int = Field(default=None)
    
    async def get_branch(self) -> Branch:
        """Get the main branch for this repo."""
        if not self.main_branch_id:
            raise ValueError("Main branch ID is not set. The model has not been saved yet.")
        
        return await PostgresOperations.get_branch(self.main_branch_id)
    
    async def get_current_turn(self) -> Optional[Turn]:
        """
        Get the current turn for this repo.
        
        Returns:
            The current turn, or None if no turn exists
        """
        branch = await self.get_branch()
        return branch.last_turn
    
    async def commit_turn(self, message: Optional[str] = None) -> int:
        """
        Commit the current turn and create a new one.
        
        Args:
            message: Optional message for the turn
            
        Returns:
            The ID of the new turn
        """
        if not self.main_branch_id:
            raise ValueError("Main branch ID is not set. The model has not been saved yet.")
        
        return await PostgresOperations.commit_turn(self.main_branch_id, message)
    
    
MODEL = TypeVar("MODEL", bound="Model")



class Relation(Generic[MODEL]):
    """
    A relation between models.
    
    This class provides methods for querying related models.
    """
    model_cls: Type[MODEL]
    rel_field: str
    instance: Model | None = None
    
    def __init__(self, model_cls: Type[MODEL], rel_field: str):
        self.model_cls = model_cls
        self.rel_field = rel_field
        self.instance = None
    
    def set_instance(self, instance: Model):
        """Set the instance ID for this relation."""
        self.instance = instance
    
    def _build_query_set(self):
        """Build a query set for this relation."""
        if not self.instance:
            raise ValueError("Instance is not set")
        return self.model_cls.query(partition_id=self.instance.id)
    
    def all(self):
        """Get all related models."""
        return self._build_query_set()
    
    def filter(self, **kwargs):
        """Filter related models."""
        qs = self._build_query_set()
        return qs.filter(**kwargs)
    
    def limit(self, limit: int):
        """Limit the number of related models."""
        qs = self._build_query_set()
        return qs.limit(limit)
    
    async def add(self, obj: MODEL, turn: Optional[int | Turn] = None, branch: Optional[int | Branch] = None) -> MODEL:
        """
        Add a related model.
        
        If the model has a _repo attribute, it will be saved with the appropriate branch.
        """
        if not isinstance(obj, self.model_cls):
            raise ValueError("Object is not of type {}".format(self.model_cls.__name__))
        # Set the relation field
        setattr(obj, self.rel_field, self.instance.id)
        
        if self.model_cls._is_versioned:
            turn_id, branch_id = parse_version_params(turn, branch)
            return await obj.save(turn=turn_id, branch=branch_id)
        else:
            return await obj.save()
        # Save the object (branch will be determined by the model's repo)
        
        
    
    
    
    # @classmethod
    # def __get_pydantic_core_schema__(
    #     cls, 
    #     _source_type: Any, 
    #     _handler: Callable[[Any], pydantic_core.core_schema.CoreSchema]
    # ) -> pydantic_core.core_schema.CoreSchema:
    #     from pydantic_core import core_schema
    #     # Use a simple any schema since we're handling serialization ourselves
    #     return core_schema.any_schema()
    
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        def validate_custom(value, info):
            if isinstance(value, cls):
                relation_model = get_relation_model(value)
                if issubclass(relation_model, Model):
                    return value
                else:
                    raise TypeError("Relation must be a Model")
            else:
                raise TypeError("Invalid type for Relation; expected Relation instance")
        return pydantic_core.core_schema.with_info_plain_validator_function(validate_custom)

def get_relation_model(cls):
    """Get the model class from a relation type."""
    args = get_args(cls)
    if len(args) != 1:
        raise ValueError("Relation model must have exactly one argument")
    return args[0]

def make_default_factory(model_cls, rel_field):
    """Create a default factory for a relation field."""
    def default_factory():
        return Relation(model_cls=model_cls, rel_field=rel_field)
    return default_factory
    # return lambda: Relation(model_cls=model_cls, rel_field=rel_field)
    
    
    
    
    
