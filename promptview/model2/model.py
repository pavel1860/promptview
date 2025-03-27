from typing import TYPE_CHECKING, Any, Dict, Generic, Optional, Type, TypeVar, Callable, cast, ForwardRef, get_args, get_origin
from pydantic import BaseModel, Field, PrivateAttr
from pydantic.config import JsonDict
from pydantic._internal._model_construction import ModelMetaclass
from pydantic.fields import FieldInfo
import pydantic_core
import datetime as dt

from promptview.model2.context import Context
from promptview.model2.fields import KeyField, ModelField
from promptview.model2.namespace_manager import NamespaceManager
from promptview.model2.base_namespace import DatabaseType, NSManyToManyRelationInfo, NSRelationInfo, Namespace, QuerySet, QuerySetSingleAdapter
from promptview.model2.versioning import Branch, Turn
from promptview.model2.postgres.operations import PostgresOperations
from promptview.utils.string_utils import camel_to_snake


if TYPE_CHECKING:
    from promptview.prompt.block6 import Block

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


            
class ModelMeta(ModelMetaclass, type):
    """Metaclass for Model
    
    This metaclass handles the registration of models with the namespace manager
    and the processing of fields.
    """
    
    def __new__(cls, name, bases, dct):
        # Use the standard Pydantic metaclass to create the class
        
        
        # Skip processing for the base Model class
        if name == "Model" or name == "RepoModel" or name == "ArtifactModel" or name == "ContextModel":
            cls_obj = super().__new__(cls, name, bases, dct)
            return cls_obj
        
        # Get model name and namespace
        model_name = name
        db_type = get_dct_private_attributes(dct, "_db_type", "postgres")
        namespace_name = get_dct_private_attributes(dct, "_namespace_name", build_namespace(model_name))        
        
        # Check if this is a repo model or an artifact model
        is_repo = len(bases) >= 1 and bases[0].__name__ == "RepoModel"
                
        # If _repo is specified, the model is automatically versioned
        is_versioned = get_dct_private_attributes(dct, "_is_versioned", False) or (len(bases) >= 1 and (bases[0].__name__ == "ArtifactModel" or bases[0].__name__ == "ContextModel"))
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
            if field_origin and (field_origin == Relation or field_origin == ManyRelation):
                # Get the model class from the relation                                
                
                primary_key = extra.get("primary_key") or "id"
                foreign_key = extra.get("foreign_key")
                on_delete=extra.get("on_delete", "CASCADE")
                on_update=extra.get("on_update", "CASCADE")
                
                if not foreign_key:
                    raise ValueError("foreign_key is required for one_to_many relation")
                
                print(primary_key, foreign_key, on_delete, on_update)
                if not foreign_key:
                    raise ValueError("foreign_key is required for one_to_many relation")
                if field_origin == Relation:
                    foreign_cls = get_one_to_many_relation_model(field_type)                    
                    relation_field = ns.add_relation(
                        name=field_name,
                        primary_key=primary_key,
                        foreign_key=foreign_key,
                        foreign_cls=foreign_cls,
                        on_delete=on_delete,
                        on_update=on_update,
                    )
                    field_info.default_factory = make_relation_default_factory(ns, relation_field)

                else:  # many to many relation
                    foreign_cls, junction_cls = get_many_to_many_relation_model(field_type)
                    junction_keys = extra.get("junction_keys", None)
                    relation_field = ns.add_many_relation(
                        name=field_name,
                        primary_key=primary_key,
                        foreign_key=foreign_key,
                        foreign_cls=foreign_cls,
                        junction_cls=junction_cls,
                        junction_keys=junction_keys,
                        on_delete=on_delete,
                        on_update=on_update,
                    )                
                    field_info.default_factory = make_many_relation_default_factory(ns, relation_field)
                
                relations[field_name] = relation_field
                # Skip adding this field to the namespace
                continue
            
            # Add field to namespace
            ns.add_field(field_name, field_type, extra)
        
        # Set namespace name and relations on the class
        cls_obj = super().__new__(cls, name, bases, dct)
        ns.set_model_class(cls_obj)
        cls_obj._namespace_name = namespace_name
        cls_obj._is_versioned = is_versioned
        # Register relations with the namespace manager
        # for relation_name, relation_info in relations.items():
            # target_cls: Any = relation_info["target_type"]
            # # If target_type is a ForwardRef, we need to resolve it later
            # target_namespace = None
            # if not isinstance(target_cls, ForwardRef) and hasattr(target_cls, "_namespace_name"):
            #     target_namespace = target_cls._namespace_name
            
            # # Get the key, on_delete, and on_update values
            # key = relation_info.get("key", "id")
            # on_delete = relation_info.get("on_delete", "CASCADE")
            # on_update = relation_info.get("on_update", "CASCADE")
            # Register the relation
            
            
            # NamespaceManager.register_relation(
            #     source_namespace=namespace_name,
            #     relation_name=relation_name,
            #     target_namespace=target_namespace,
            #     target_forward_ref=target_cls if isinstance(target_cls, ForwardRef) else None,
            #     key=key,
            #     on_delete=on_delete,
            #     on_update=on_update,
            # )

        
        return cls_obj
    
    
    
    
MODEL = TypeVar("MODEL", bound="Model")

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
    def get_namespace(cls) -> Namespace:
        """Get the namespace for this model"""
        return NamespaceManager.get_namespace(cls.get_namespace_name())
    
    @classmethod
    def get_key_field(cls) -> str:
        """Get the key field for this model"""
        ns = cls.get_namespace()
        return ns.primary_key.name
    
    @property
    def primary_id(self) -> Any:
        """Get the key for this model"""
        return getattr(self, self.get_key_field())
    
    @classmethod
    async def initialize(cls):
        """Initialize the model (create table)"""
        ns = cls.get_namespace()
        await ns.create_namespace()
    
    def _get_relation_fields(self):
        """Get the names of relation fields."""
        ns = self.get_namespace()
        return list(ns._relations.keys())
    
    def _update_relation_instance(self):
        """Update the instance for all relations."""
        # Get the ID from the model instance
        # The ID field should be defined by the user
        if not hasattr(self, "id"):
            return
        
        for field_name in self._get_relation_fields():
            relation = getattr(self, field_name)
            if relation:
                relation.set_primary_instance(self)
                
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
                
        ns = self.get_namespace()
        data = self._payload_dump()
        result = await ns.save(data, id=self.primary_id)
        # Update instance with returned data (e.g., ID)
        for key, value in result.items():
            setattr(self, key, value)
        
        # Update relation instance IDs
        self._update_relation_instance()
        
        return self
    
    @classmethod
    async def get(cls: Type[MODEL], id: Any) -> MODEL:
        """Get a model instance by ID"""
        ns = cls.get_namespace()
        data = await ns.get(id)
        if data is None:
            raise ValueError(f"Model with ID {id} not found")
        instance = cls(**data)
        instance._update_relation_instance()
        return instance
    
    @classmethod
    async def get_or_none(cls: Type[MODEL], id: Any) -> MODEL | None:
        """Get a model instance by ID or None if it doesn't exist"""
        ns = cls.get_namespace()
        data = await ns.get(id)
        instance = cls(**data) if data else None
        if not instance:
            return None
        instance._update_relation_instance()
        return instance
    
    @classmethod
    def query(cls: Type[MODEL], partition_id: int | None = None, branch: int | Branch | None = None) -> "QuerySet[MODEL]":
        """
        Create a query for this model
        
        Args:
            branch: Optional branch ID to query from
        """            
        ns = cls.get_namespace()
        return ns.query(None, branch)


# No need for the ModelFactory class anymore




class ArtifactModel(Model):
    """
    A model that is versioned and belongs to a repo.
    """
    branch_id: int = ModelField(default=None)
    turn_id: int = ModelField(default=None)
    _repo: str = PrivateAttr(default=None)  # Namespace of the repo model
    
    
    async def save(self, turn: Optional[int | Turn], branch: Optional[int | Branch] = None):
        """
        Save the artifact model instance to the database
        
        Args:
            branch: Optional branch ID to save to
            turn: Optional turn ID to save to
        """        
        
                
        ns = NamespaceManager.get_namespace(self.__class__.get_namespace_name())
        data = self._payload_dump()
        result = await ns.save(data, id=self.primary_id, branch=branch, turn=turn)
        # Update instance with returned data (e.g., ID)
        for key, value in result.items():
            setattr(self, key, value)
        
        # Update relation instance IDs
        self._update_relation_instance()
        
        return self

    
    
class ContextModel(ArtifactModel):
    # id: int = KeyField(primary_key=True)
    # created_at: dt.datetime = ModelField(default=None)
    
    @classmethod
    def from_block(cls, block: "Block") -> "ContextModel":
        raise NotImplementedError("ContextModel.from_block is not implemented")
    
    def to_block(self, ctx: "Context") -> "Block":
        raise NotImplementedError("ContextModel.to_block is not implemented")
    
    @classmethod
    def query(cls: Type[MODEL], partition_id: int | None = None, branch: int | Branch | None = None) -> "QuerySet[MODEL]":
        """
        Create a query for this model
        
        Args:
            branch: Optional branch ID to query from
        """
        ns = cls.get_namespace()
        return ns.query(partition_id, branch)


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
    
    


PRIMARY_MODEL = TypeVar("PRIMARY_MODEL", bound="Model")
FOREIGN_MODEL = TypeVar("FOREIGN_MODEL", bound="Model")


class BaseRelation:
    _primary_instance: Model | None = None
    _partition_id: int | None = None
    namespace: Namespace
    
    def __init__(self, namespace: Namespace):
        self._primary_instance = None
        self.namespace = namespace
        
    @property
    def primary_cls(self) -> Type[Model]:
        if self._primary_instance is None:
            raise ValueError("Primary class is not set")
        return self._primary_instance.__class__
    
    @property
    def is_context_model(self) -> bool:
        return self.namespace.is_context
    
    @property
    def primary_instance(self) -> Model:
        if self._primary_instance is None:
            raise ValueError("Instance is not set")
        return self._primary_instance
    
    def set_primary_instance(self, instance: Model):
        """Set the instance ID for this relation."""
        self._primary_instance = instance
        
    def _build_query_set(self):
        raise NotImplementedError("Subclasses must implement this method")
    
    @classmethod
    def validate_models(cls, value: Any) -> bool:
        raise NotImplementedError("Subclasses must implement this method")

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        def validate_custom(value, info):
            if isinstance(value, cls):
                if cls.validate_models(value):
                    return value
                else:
                    raise TypeError("Relation must be a Model")
            else:
                raise TypeError("Invalid type for Relation; expected Relation instance")
        return pydantic_core.core_schema.with_info_plain_validator_function(validate_custom)


class Relation(Generic[FOREIGN_MODEL], BaseRelation):
    """
    A relation between models.
    
    This class provides methods for querying related models.
    """    
    relation_field: NSRelationInfo
    
    
    def __init__(self, namespace: Namespace, relation_field: NSRelationInfo):
        super().__init__(namespace)
        self.relation_field = relation_field
        

    
    def _build_query_set(self) -> "QuerySet[FOREIGN_MODEL]":
        """Build a query set for this relation."""
        if not self.primary_instance:
            raise ValueError("Instance is not set")
        # return self.namespace.query(None)
        # return self.primary_cls.query(partition_id=self.primary_instance.primary_id)
        if self.is_context_model:
            return self.namespace.query(partition_id=self.primary_instance.primary_id)
        else:
            return self.relation_field.foreign_namespace.query(filters={self.relation_field.foreign_key: self.primary_instance.primary_id})
    
    def all(self):
        """Get all related models."""
        return self._build_query_set()
    
    def filter(self, filter_fn: Callable[[FOREIGN_MODEL], bool] | None = None, **kwargs) -> "QuerySet[FOREIGN_MODEL]":
        """Filter related models."""
        qs = self._build_query_set()
        return qs.filter(filter_fn=filter_fn,**kwargs)
    
    def first(self) -> "QuerySetSingleAdapter[FOREIGN_MODEL]":
        """Get the first related model."""
        qs = self._build_query_set()
        return qs.first()
    
    def last(self) -> "QuerySetSingleAdapter[FOREIGN_MODEL]":
        """Get the last related model."""
        qs = self._build_query_set()
        return qs.last()
    
    
    def limit(self, limit: int) -> "QuerySet[FOREIGN_MODEL]":
        """Limit the number of related models."""
        qs = self._build_query_set()
        return qs.limit(limit)
    
    async def add(self, obj: FOREIGN_MODEL, turn: Optional[int | Turn] = None, branch: Optional[int | Branch] = None) -> FOREIGN_MODEL:
        """
        Add a related model.
        
        If the model has a _repo attribute, it will be saved with the appropriate branch.
        """
        if self.primary_instance is None:
            raise ValueError("Instance is not set")
        if not isinstance(obj, self.relation_field.foreign_cls):
            raise ValueError("Object ({}) is not of type {}".format(obj.__class__.__name__, self.relation_field.foreign_cls.__name__))
        # Set the relation field
        setattr(obj, self.relation_field.foreign_key, self.primary_instance.primary_id)
        
        if obj._is_versioned:
            return await obj.save(turn=turn, branch=branch)
        else:
            return await obj.save()
        # Save the object (branch will be determined by the model's repo)

    
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        def validate_custom(value, info):
            if isinstance(value, cls):
                relation_model = get_one_to_many_relation_model(value)
                if issubclass(relation_model, Model):
                    return value
                else:
                    raise TypeError("Relation must be a Model")
            else:
                raise TypeError("Invalid type for Relation; expected Relation instance")
        return pydantic_core.core_schema.with_info_plain_validator_function(validate_custom)




JUNCTION_MODEL = TypeVar("JUNCTION_MODEL", bound="Model")

class ManyRelation(Generic[FOREIGN_MODEL, JUNCTION_MODEL], BaseRelation):
    """
    A relation between models.
    
    This class provides methods for querying related models.
    """        
    relation_field: NSManyToManyRelationInfo
    def __init__(self, namespace: Namespace, relation_field: NSManyToManyRelationInfo):
        super().__init__(namespace)  
        self.relation_field = relation_field      
            
    def get_relation_key_params(self, obj: FOREIGN_MODEL, kwargs: dict[str, Any]):
        params = {}
        # params[self.relation_field.primary_key] = self.primary_instance.primary_id
        # params[self.relation_field.foreign_key] = obj.primary_id
        params[self.relation_field.junction_primary_key] = self.primary_instance.primary_id
        params[self.relation_field.junction_foreign_key] = obj.primary_id
        for key, value in kwargs.items():
            params[key] = value
        return params

    # def _build_query_set(self):
    #     """Build a query set for this relation."""
    #     if not self.primary_instance:
    #         raise ValueError("Instance is not set")
    #     return self.primary_cls.query(partition_id=self.primary_instance.primary_id)
    
    def _build_query_set(self):
        """Build a query set for this relation."""
        if not self.primary_instance:
            raise ValueError("Instance is not set")
        return self.relation_field.foreign_namespace.query(
            partition_id=self.primary_instance.primary_id if self.is_context_model else None,
            # joins=[{
            #     "primary_table": self.relation_field.junction_table,
            #     "primary_key": self.relation_field.junction_foreign_key,
            #     "foreign_table": self.relation_field.foreign_table,
            #     "foreign_key": self.relation_field.foreign_key,
            # }],
            select=[self.relation_field.foreign_namespace.select_fields()],
            joins=[{
                "primary_table": self.relation_field.foreign_table,
                "primary_key": self.relation_field.foreign_key,
                "foreign_table": self.relation_field.junction_table,
                "foreign_key": self.relation_field.junction_foreign_key,
            }],
            filters={self.relation_field.junction_primary_key: self.primary_instance.primary_id},            
        )
    
    def all(self):
        """Get all related models."""
        return self._build_query_set()
    
    def filter(self, filter_fn: Callable[[FOREIGN_MODEL], bool] | None = None, **kwargs) -> QuerySet[FOREIGN_MODEL]:
        """Filter related models."""
        qs = self._build_query_set()
        return qs.filter(filter_fn=filter_fn,**kwargs)
    
    def first(self) -> QuerySetSingleAdapter[FOREIGN_MODEL]:
        """Get the first related model."""
        qs = self._build_query_set()
        return qs.first()
    
    def last(self) -> QuerySetSingleAdapter[FOREIGN_MODEL]:
        """Get the last related model."""
        qs = self._build_query_set()
        return qs.last()
    
    
    def limit(self, limit: int) -> QuerySet[FOREIGN_MODEL]:
        """Limit the number of related models."""
        qs = self._build_query_set()
        return qs.limit(limit)
        
    
    async def add(self, obj: FOREIGN_MODEL, turn: Optional[int | Turn] = None, branch: Optional[int | Branch] = None, **kwargs) -> FOREIGN_MODEL:
        """
        Add a list of related models.
        """
        if self.primary_instance is None or self.relation_field.junction_cls is None:
            raise ValueError("Instance or many_relation_cls is not set")

        # obj = await super(ManyRelation, self).add(obj, turn, branch)        
        if self.primary_cls._is_versioned:
            obj = await obj.save(turn=turn, branch=branch)
        else:
            obj = await obj.save()
            
        relation = self.relation_field.junction_cls(**self.get_relation_key_params(obj, kwargs))            
        if self.primary_cls._is_versioned:
            relation = await relation.save(turn=turn, branch=branch)
        else:
            relation = await relation.save()
        setattr(obj, self.relation_field.foreign_key, relation.primary_id)
        await obj.save()
        return obj
    
    
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
            # print(value)
            # print("---------------")
            # print(info)
            # print(source)
            # print(handler)
            if isinstance(value, cls):
                relation_model, target_model = get_many_to_many_relation_model(value)
                if issubclass(relation_model, Model) and issubclass(target_model, Model):
                    return value
                else:
                    raise TypeError("Relation must be a Model")
            elif isinstance(value, list):
                for item in value:
                    relation_model, target_model = get_many_to_many_relation_model(item)
                    if not issubclass(relation_model, Model) or not issubclass(target_model, Model):
                        raise TypeError("Relation must be a Model")
                return ManyRelation(cls.namespace, self.relation_field)
            
            else:
                print(value)
                raise TypeError("Invalid type for Relation; expected Relation instance")
        return pydantic_core.core_schema.with_info_plain_validator_function(validate_custom)




def get_one_to_many_relation_model(cls):
    """Get the model class from a relation type."""
    args = get_args(cls)
    if len(args) != 1:
        raise ValueError("Relation model must have exactly one argument")
    return args[0]


def get_many_to_many_relation_model(cls):
    """Get the model class from a relation type."""
    args = get_args(cls)
    if len(args) != 2:
        raise ValueError("Relation model must have exactly one argument")
    return args[0], args[1]



def make_relation_default_factory(namespace: Namespace, relation_field: NSRelationInfo):
    """Create a default factory for a relation field."""
    def relation_default_factory():
        return Relation(namespace, relation_field)
    return relation_default_factory
    
    
    
    
def make_many_relation_default_factory(namespace: Namespace, relation_field: NSManyToManyRelationInfo):
    """Create a default factory for a many relation field."""
    def many_relation_default_factory():
        return ManyRelation(namespace, relation_field)
    return many_relation_default_factory

