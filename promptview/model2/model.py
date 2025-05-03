import contextvars
from typing import TYPE_CHECKING, Any, Dict, Generic, Iterable, Iterator, List, Optional, Set, Tuple, Type, TypeVar, Callable, cast, ForwardRef, get_args, get_origin
import uuid
from pydantic import BaseModel, Field, PrivateAttr
from pydantic.config import JsonDict
from pydantic._internal._model_construction import ModelMetaclass
from pydantic.fields import FieldInfo
import pydantic_core
import datetime as dt


from promptview.model2.context import Context
from promptview.model2.fields import KeyField, ModelField
from promptview.model2.namespace_manager import NamespaceManager
from promptview.model2.base_namespace import DatabaseType, NSFieldInfo, NSManyToManyRelationInfo, NSRelationInfo, Namespace, QuerySet, QuerySetSingleAdapter
from promptview.model2.postgres.query_set3 import SelectQuerySet
from promptview.model2.query_filters import SelectFieldProxy



from promptview.utils.model_utils import unpack_list_model
from promptview.utils.string_utils import camel_to_snake


if TYPE_CHECKING:
    from promptview.model2.version_control_models import Branch
    from promptview.prompt.block6 import Block
    from promptview.llms.llm3 import OutputModel

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


ARTIFACT_RESERVED_FIELDS = ["id", "artifact_id", "version", "branch_id", "turn_id", "created_at", "updated_at", "deleted_at"]

AUTH_RESERVED_FIELDS = ["id", "name", "email", "emailVerified", "image", "is_admin"]


def check_reserved_fields(bases: Any, name: str, field_name: str):
    if bases[0].__name__ == "ArtifactModel":
        if field_name in ARTIFACT_RESERVED_FIELDS:
            raise ValueError(f"""Field "{field_name}" in ArtifactModel "{name}" is reserved for internal use. use a different name. {", ".join(ARTIFACT_RESERVED_FIELDS)} are reserved.""")
    elif bases[0].__name__ == "AuthModel":
        if field_name in AUTH_RESERVED_FIELDS:
            raise ValueError(f"""Field "{field_name}" in AuthModel "{name}" is reserved for internal use. use a different name. {", ".join(AUTH_RESERVED_FIELDS)} are reserved.""")

def check_if_artifact_model(bases: Any, name: str):
    if len(bases) >= 1 and bases[0].__name__ == "ArtifactModel":
        return True
    return False

def check_if_context_model(bases: Any, name: str):
    if len(bases) >= 1 and bases[0].__name__ == "ContextModel":
        return True
    return False


def unpack_extra(field_info: FieldInfo) -> dict[str, Any]:
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
    return extra

def unpack_relation_extra(extra: dict[str, Any], field_origin: Type[Any], is_versioned: bool) -> tuple[str, str, list[str] | None, str, Type[Any] | None, str, str]:
    primary_key = extra.get("primary_key") or ("artifact_id" if is_versioned else "id")
    foreign_key = extra.get("foreign_key")
    on_delete=extra.get("on_delete", "CASCADE")
    on_update=extra.get("on_update", "CASCADE")
    junction_keys = extra.get("junction_keys", None)
    junction_model = extra.get("junction_model", None)
    relation_type = "one_to_one"                
    if field_origin is list and junction_keys is not None:
        if junction_model is not None:
            relation_type = "many_to_many"
        else:
            relation_type = "one_to_many"
    
    if not foreign_key:
        raise ValueError("foreign_key is required for one_to_many relation")
    
    print(primary_key, foreign_key, on_delete, on_update)
    if not foreign_key:
        raise ValueError("foreign_key is required for one_to_many relation")
    
    return primary_key, foreign_key, junction_keys, relation_type, junction_model, on_delete, on_update



class ModelMeta(ModelMetaclass, type):
    """Metaclass for Model
    
    This metaclass handles the registration of models with the namespace manager
    and the processing of fields.
    """
    
    def __new__(cls, name, bases, dct):
        # Use the standard Pydantic metaclass to create the class
        
        
        # Skip processing for the base Model class
        # if name == "Model" or name == "RepoModel" or name == "ArtifactModel" or name == "ContextModel" or name == "AuthModel" or name == "TurnModel":
        if dct.get("_is_base", False):
            cls_obj = super().__new__(cls, name, bases, dct)
            return cls_obj
        
        # Get model name and namespace
        model_name = name
        db_type = get_dct_private_attributes(dct, "_db_type", "postgres")
        namespace_name = get_dct_private_attributes(dct, "_namespace_name", build_namespace(model_name))
        
        
        # Check if this is a repo model or an artifact model
        is_repo = len(bases) >= 1 and bases[0].__name__ == "RepoModel"
        is_artifact = check_if_artifact_model(bases, name)
        is_context = check_if_context_model(bases, name)
        # If _repo is specified, the model is automatically versioned
        is_versioned = get_dct_private_attributes(dct, "_is_versioned", False) or (len(bases) >= 1 and (bases[0].__name__ == "ArtifactModel" or bases[0].__name__ == "ContextModel" or bases[0].__name__ == "TurnModel"))
        repo_namespace = get_dct_private_attributes(dct, "_repo", "main" if is_versioned else None)
        if repo_namespace is None and is_versioned:
            raise ValueError("RepoModel must have a repo namespace")
        
        if is_repo and is_versioned:
            raise ValueError("RepoModel cannot be versioned")
        
        # Build namespace
        ns = NamespaceManager.build_namespace(
            model_name=namespace_name, 
            db_type=db_type, 
            is_versioned=is_versioned,
            is_context=is_context,
            is_repo=is_repo, 
            is_artifact=is_artifact, 
            repo_namespace=repo_namespace
        )
        # Process fields and relations
        relations = {}
        field_extras = {}
        for field_name, field_info in dct.items():
            # Skip fields without a type annotation
            check_reserved_fields(bases, name, field_name)
            if not isinstance(field_info, FieldInfo):
                continue
            
            
            field_type = dct["__annotations__"].get(field_name)
            if field_type is None:
                continue
            
            extra = unpack_extra(field_info)
            
            # Check if this is a relation field
            
            if extra.get("is_relation", False):
                # Get the model class from the relation                                
                
                # primary_key = extra.get("primary_key") or ("artifact_id" if ns.is_versioned else "id")
                # foreign_key = extra.get("foreign_key")
                # on_delete=extra.get("on_delete", "CASCADE")
                # on_update=extra.get("on_update", "CASCADE")
                # junction_keys = extra.get("junction_keys", None)
                # junction_model = extra.get("junction_model", None)
                # relation_type = "one_to_one"                
                # if field_origin is Iterable:
                #     if junction_model is not None:
                #         relation_type = "many_to_many"
                #     else:
                #         relation_type = "one_to_many"
                
                # if not foreign_key:
                #     raise ValueError("foreign_key is required for one_to_many relation")
                
                # print(primary_key, foreign_key, on_delete, on_update)
                # if not foreign_key:
                #     raise ValueError("foreign_key is required for one_to_many relation")
                field_origin = get_origin(field_type)
                foreign_cls = None
                if field_origin is list:
                    foreign_cls = unpack_list_model(field_type)
                    if not issubclass(foreign_cls, Model) and not isinstance(foreign_cls, ForwardRef):
                        raise ValueError(f"foreign_cls must be a subclass of Model: {foreign_cls}")
                if not foreign_cls:
                    raise ValueError(f"foreign_cls is required for relation: {field_type} on Model {name}")
                    
                primary_key, foreign_key, junction_keys, relation_type, junction_cls, on_delete, on_update = unpack_relation_extra(extra, field_origin, ns.is_versioned)
                                
                if relation_type == "one_to_one" or relation_type == "one_to_many":                    
                    # foreign_cls = get_one_to_many_relation_model(field_type)                    
                    relation_field = ns.add_relation(
                        name=field_name,
                        primary_key=primary_key,
                        foreign_key=foreign_key,
                        foreign_cls=foreign_cls,
                        on_delete=on_delete,
                        on_update=on_update,
                    )
                    # field_info.default_factory = make_relation_default_factory(ns, relation_field)

                else:  # many to many relation
                    # foreign_cls, junction_cls = get_many_to_many_relation_model(field_type)
                    if junction_cls is None:
                        raise ValueError(f"junction_cls is required for many to many relation: {field_type} on Model {name}")
                    if not junction_keys:
                        raise ValueError(f"junction_keys is required for many to many relation: {field_type} on Model {name}")
                    
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
                    # field_info.default_factory = make_many_relation_default_factory(ns, relation_field)
                
                relations[field_name] = relation_field
                # Skip adding this field to the namespace
                continue
            
            # Add field to namespace
            field_extras[field_name] = extra
            # ns.add_field(field_name, field_type, extra)
        
        # Set namespace name and relations on the class
        cls_obj = super().__new__(cls, name, bases, dct)
        
        for field_name, field_info in cls_obj.model_fields.items():
            if field_name in relations:
                continue
            field_type = field_info.annotation
            # extra = field_extras.get(field_name, {})
            extra = get_extra(field_info)
            ns.add_field(field_name, field_type, extra)
        
        
        ns.set_model_class(cls_obj)
        cls_obj._namespace_name = namespace_name
        cls_obj._is_versioned = is_versioned

        
        return cls_obj
    
    # def __getattribute__(cls, name: str) -> Any:
    #     # print(cls, name)
    #     if NamespaceManager._is_initialized and name not in {"__name__", "model_fields", "__pydantic_fields__", "get_namespace", "get_namespace_name", "_namespace_name"}:        
    #         # print("entered")
    #         if name in cls.model_fields:
    #             ns = NamespaceManager.get_namespace_or_none(build_namespace(cls.__name__))
    #             if ns:
    #                 if not ns.has_field(name):
    #                     raise ValueError(f"Field {name} not found in namespace {ns.table_name}")
    #                 return SelectField(ns.get_field(name))
    #                 # return FieldComparable(name, cls.model_fields[name])
    #                 # print("table",ns.table_name, name)
    #             else:
    #                 raise ValueError(f"Namespace {build_namespace(cls.__name__)} not found")
    #     return super().__getattribute__(name)
    
    # def get_field(cls, name: str) -> SelectField:
    #     if name in cls.model_fields:
    #         ns = NamespaceManager.get_namespace_or_none(build_namespace(cls.__name__))
    #         if ns:
    #             if not ns.has_field(name):
    #                 raise ValueError(f"Field {name} not found in namespace {ns.table_name}")
    #             return SelectField(ns.get_field(name))                    
    #     raise ValueError(f"Namespace {build_namespace(cls.__name__)} not found")
    @property
    def f(cls: "Type[Model]") -> SelectFieldProxy:
        return SelectFieldProxy(cls, cls.get_namespace())
    
    
MODEL = TypeVar("MODEL", bound="Model")
JUNCTION_MODEL = TypeVar("JUNCTION_MODEL", bound="Model")

class Model(BaseModel, metaclass=ModelMeta):
    """Base class for all models
    
    This class is a simple Pydantic model with a custom metaclass.
    The ORM functionality is added by the metaclass.
    """
    # Namespace reference - will be set by the metaclass
    _is_base: bool = True
    _namespace_name: str = PrivateAttr(default=None)
    _db_type: DatabaseType = PrivateAttr(default="postgres")
    _is_versioned: bool = PrivateAttr(default=False)
    _relations: Dict[str, Dict[str, Any]] = PrivateAttr(default_factory=dict) 
    _ctx_token: contextvars.Token | None = PrivateAttr(default=None)    
    
    
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
    def current(cls) -> MODEL:
        """Get the current model in context"""
        ns = cls.get_namespace()
        return ns.get_ctx()
    
    @classmethod
    def current_or_none(cls) -> MODEL | None:
        """Get the current model in context or None if it is not set"""
        ns = cls.get_namespace()
        return ns.get_ctx_or_none()
    
    @classmethod
    async def initialize(cls):
        """Initialize the model (create table)"""
        ns = cls.get_namespace()
        await ns.create_namespace()
    
    def _get_relation_fields(self):
        """Get the names of relation fields."""
        ns = self.get_namespace()
        return list(ns._relations.keys())
    
    
    def __enter__(self):
        """Enter the context"""
        ns = self.get_namespace()
        self._ctx_token = ns.set_ctx(self)
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the context"""
        ns = self.get_namespace()
        ns.set_ctx(None)
        self._ctx_token = None
        
    
    
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
        if len(exclude) > 0:
            kwargs["exclude"] = exclude
        res = super().model_dump(*args, **kwargs)
        return res
                
    def _payload_dump(self):
        relation_fields = self._get_relation_fields()
        version_fields = ["turn_id", "branch_id", "main_branch_id", "head_id"]
            
        dump = self.model_dump(exclude={"id", "score", "_vector", *relation_fields, *version_fields})
        return dump
    
    @classmethod
    def iter_fields(cls, keys: bool = True, select: Set[str] | None = None) -> Iterator[NSFieldInfo]:
        ns = cls.get_namespace()
        return ns.iter_fields(keys, select)
    
    async def save(self, *args, **kwargs):
        """
        Save the model instance to the database
        """        
                
        ns = self.get_namespace()        
        result = await ns.save(self)
        # Update instance with returned data (e.g., ID)
        for key, value in result.items():
            setattr(self, key, value)
        
        # Update relation instance IDs
        self._update_relation_instance()
        
        return self
    
    async def delete(self, *args, **kwargs):
        """
        Delete the model instance from the database
        """
        ns = self.get_namespace()
        result = await ns.delete(id=self.primary_id)
        return result
    
    
    async def add(self, model: MODEL, **kwargs) -> MODEL:
        """Add a model instance to the database"""
        ns = self.get_namespace()
        relation = ns.get_relation_by_type(model.__class__)
        if not relation:
            raise ValueError(f"Relation model not found for type: {model.__class__.__name__}")
        if isinstance(relation, NSManyToManyRelationInfo):
            result = await model.save()
            junction = relation.create_junction(self, result)            
            junction = await junction.save()            
        else:
            key = getattr(self, relation.primary_key)
            setattr(model, relation.foreign_key, key)
            result = await model.save()
        return result
    
    
    async def add_rel(self, relation: JUNCTION_MODEL, model: MODEL) -> Tuple[JUNCTION_MODEL, MODEL]:
        ns = self.get_namespace()
        relation = ns.get_relation_by_type(model.__class__)
        if not relation:
            raise ValueError(f"Relation model not found for type: {model.__class__.__name__}")
        if isinstance(relation, NSManyToManyRelationInfo):
            result = await model.save()
            junction = relation.create_junction(self, result)            
            junction = await junction.save()
        else:
            raise ValueError("Relation is not a many to many relation")
        return junction, result
    
    @classmethod
    async def get(cls: Type[MODEL], id: Any) -> MODEL:
        """Get a model instance by ID"""
        ns = cls.get_namespace()
        data = await ns.get(id)
        if data is None:
            raise ValueError(f"Model '{cls.__name__}' with ID '{id}' not found")
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
    def query(cls: Type[MODEL], branch: "int | Branch | None" = None, turn: "int | Turn | None" = None, **kwargs) -> "SelectQuerySet[MODEL]":
        """
        Create a query for this model
        
        Args:
            branch: Optional branch ID to query from
        """
        from promptview.model2.version_control_models import get_branch_id, get_turn_id
        branch_id = get_branch_id(branch)
        ns = cls.get_namespace()
        return ns.query(branch_id=branch_id, **kwargs)
    
    
    # def join(self, model: Type[MODEL], partition: Partition | None = None, branch: Branch | int = 1) -> "QuerySet[MODEL]":
                    
    #     ns = self.get_namespace()
    #     rel_field = ns.get_relation_by_type(model)
    #     if not rel_field:
    #         raise ValueError(f"relation is not existing for type: {model.__name__}")
    #     relation = getattr(self, rel_field.name)
    #     if not relation:
    #         raise ValueError("relation is not existing")
    #     query = relation.build_query(partition)
    #     return query
    
    # def join(self, model: Type[MODEL], partition: Partition | None = None, branch: Branch | int = 1) -> "QuerySet[MODEL]":
    #     partition_id = None
    #     if partition:
    #         partition_id = partition.id
    #     ns = self.get_namespace()
    #     rel_field = ns.get_relation_by_type(model)
    #     if not rel_field:
    #         raise ValueError(f"relation is not existing for type: {model.__name__}")
    #     if issubclass(rel_field.__class__, NSRelationInfo):
    #         if ns.is_context:
    #             return ns.query(partition_id=partition_id)
    #         else:
    #             return rel_field.foreign_namespace.query(partition_id=partition_id, filters={rel_field.foreign_key: self.primary_id})
    #     else:
    #         return rel_field.foreign_namespace.query(
    #             partition_id=partition,
    #             # joins=[{
    #             #     "primary_table": self.relation_field.junction_table,
    #             #     "primary_key": self.relation_field.junction_foreign_key,
    #             #     "foreign_table": self.relation_field.foreign_table,
    #             #     "foreign_key": self.relation_field.foreign_key,
    #             # }],
    #             select=[rel_field.foreign_namespace.select_fields()],
    #             joins=[{
    #                 "primary_table": rel_field.foreign_table,
    #                 "primary_key": rel_field.foreign_key,
    #                 "foreign_table": rel_field.junction_table,
    #                 "foreign_key": rel_field.junction_foreign_key,
    #             }],
    #             filters={self.relation_field.junction_primary_key: self.primary_id},            
    #         )
        
            
        # relation = getattr(self, rel_field.name)
        # if not relation:
        #     raise ValueError("relation is not existing")
        # query = relation.build_query(partition)
        # return query
        


# No need for the ModelFactory class anymore
def get_extra(field_info: FieldInfo) -> dict[str, Any]:
    extra_json = field_info.json_schema_extra
    extra: Dict[str, Any] = {}
    if extra_json is not None:
        if isinstance(extra_json, dict):
            extra = dict(extra_json)
    return extra



# class ArtifactModel(Model):
#     """
#     A model that is versioned and belongs to a repo.
#     """
#     id: int = KeyField(primary_key=True)
#     artifact_id: uuid.UUID = KeyField(default=None, type="uuid")
#     version: int = ModelField(default=1)    
#     branch_id: int = ModelField(foreign_key=True)
#     turn_id: int = ModelField(foreign_key=True)    
#     created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
#     updated_at: dt.datetime | None = ModelField(default=None)
#     deleted_at: dt.datetime | None = ModelField(default=None)
#     _repo: str = PrivateAttr(default=None)  # Namespace of the repo model
    
    
#     async def save(self, turn: int | Turn | None = None, branch: int | Branch | None = None):
#         """
#         Save the artifact model instance to the database
        
#         Args:
#             branch: Optional branch ID to save to
#             turn: Optional turn ID to save to
#         """        

#         ns = NamespaceManager.get_namespace(self.__class__.get_namespace_name())
#         result = await ns.save(self)
#         # Update instance with returned data (e.g., ID)
#         for key, value in result.items():
#             setattr(self, key, value)
        
#         # Update relation instance IDs
#         self._update_relation_instance()
        
#         return self
    
#     @classmethod
#     async def get_artifact(cls: Type[MODEL], artifact_id: uuid.UUID, version: int | None = None):
#         """
#         Get an artifact model instance by artifact ID and version
#         """
#         ns = cls.get_namespace()
#         data = await ns.get_artifact(artifact_id, version)
#         if data is None:
#             raise ValueError(f"Artifact '{artifact_id}' with version '{version}' not found")
#         instance = cls(**data)
#         instance._update_relation_instance()
#         return instance
    
    
#     async def delete(self, *args, **kwargs):
#         """
#         Delete the artifact model instance from the database
#         """
#         ns = self.get_namespace()
#         data = self._payload_dump()
#         result = await ns.delete(data=data, id=self.primary_id)
#         return result

    
    
# class ContextModel(ArtifactModel):
#     # id: int = KeyField(primary_key=True)
#     # created_at: dt.datetime = ModelField(default=None)
    
#     @classmethod
#     def from_block(cls, block: "Block", output_model: "OutputModel | None" = None) -> "ContextModel":
#         raise NotImplementedError("ContextModel.from_block is not implemented")
    
    
#     def to_block(self, ctx: "Context") -> "Block":
#         raise NotImplementedError("ContextModel.to_block is not implemented")
    
#     @classmethod
#     def query(cls: Type[MODEL], partition_id: int | None = None, branch: int | Branch | None = None) -> "QuerySet[MODEL]":
#         """
#         Create a query for this model
        
#         Args:
#             branch: Optional branch ID to query from
#         """
#         ns = cls.get_namespace()
#         return ns.query(partition_id, branch)


    
    


# PRIMARY_MODEL = TypeVar("PRIMARY_MODEL", bound="Model")
# FOREIGN_MODEL = TypeVar("FOREIGN_MODEL", bound="Model")


# class BaseRelation:
#     _primary_instance: Model | None = None
#     _partition_id: int | None = None
#     namespace: Namespace
    
#     def __init__(self, namespace: Namespace):
#         self._primary_instance = None
#         self.namespace = namespace
        
#     @property
#     def primary_cls(self) -> Type[Model]:
#         if self._primary_instance is None:
#             raise ValueError("Primary class is not set")
#         return self._primary_instance.__class__
    
#     @property
#     def is_context_model(self) -> bool:
#         return self.namespace.is_context
    
#     @property
#     def primary_instance(self) -> Model:
#         if self._primary_instance is None:
#             raise ValueError("Instance is not set")
#         return self._primary_instance
    
#     def set_primary_instance(self, instance: Model):
#         """Set the instance ID for this relation."""
#         self._primary_instance = instance
        
#     def _build_query_set(self):
#         raise NotImplementedError("Subclasses must implement this method")
    
#     @classmethod
#     def validate_models(cls, value: Any) -> bool:
#         raise NotImplementedError("Subclasses must implement this method")

#     @classmethod
#     def __get_pydantic_core_schema__(cls, source, handler):
#         def validate_custom(value, info):
#             if isinstance(value, cls):
#                 if cls.validate_models(value):
#                     return value
#                 else:
#                     raise TypeError("Relation must be a Model")
#             else:
#                 raise TypeError("Invalid type for Relation; expected Relation instance")
#         return pydantic_core.core_schema.with_info_plain_validator_function(validate_custom)


# class Relation(Generic[FOREIGN_MODEL], BaseRelation):
#     """
#     A relation between models.
    
#     This class provides methods for querying related models.
#     """    
#     relation_field: NSRelationInfo
    
    
#     def __init__(self, namespace: Namespace, relation_field: NSRelationInfo):
#         super().__init__(namespace)
#         self.relation_field = relation_field
        

    
#     def _build_query_set(self) -> "QuerySet[FOREIGN_MODEL]":
#         """Build a query set for this relation."""
#         if not self.primary_instance:
#             raise ValueError("Instance is not set")
#         # return self.namespace.query(None)
#         # return self.primary_cls.query(partition_id=self.primary_instance.primary_id)
#         if self.is_context_model:
#             return self.namespace.query(partition_id=self.primary_instance.primary_id)
#         else:
#             return self.relation_field.foreign_namespace.query(filters={self.relation_field.foreign_key: self.primary_instance.primary_id})
        
#     def build_query(self, partition):
#         partition_id = partition.id
#         if self.is_context_model:
#             return self.namespace.query(partition_id=partition_id)
#         else:
#             return self.relation_field.foreign_namespace.query(partition_id=partition_id, filters={self.relation_field.foreign_key: self.primary_instance.primary_id})
    
#     def all(self):
#         """Get all related models."""
#         return self._build_query_set()
    
#     def filter(self, filter_fn: Callable[[FOREIGN_MODEL], bool] | None = None, **kwargs) -> "QuerySet[FOREIGN_MODEL]":
#         """Filter related models."""
#         qs = self._build_query_set()
#         return qs.filter(filter_fn=filter_fn,**kwargs)
    
    
#     def last(self) -> "QuerySetSingleAdapter[FOREIGN_MODEL]":
#         """Get the last related model."""
#         qs = self._build_query_set()
#         return qs.last()
    
    
#     def tail(self, limit: int = 10) -> "QuerySet[FOREIGN_MODEL]":
#         """Get the last N related models."""
#         qs = self._build_query_set()
#         return qs.tail(limit)
    
#     def first(self) -> "QuerySetSingleAdapter[FOREIGN_MODEL]":
#         """Get the first related model."""
#         qs = self._build_query_set()
#         return qs.first()
    
    
#     def head(self, limit: int = 10) -> "QuerySet[FOREIGN_MODEL]":
#         """Get the first N related models."""
#         qs = self._build_query_set()
#         return qs.head(limit)
    
#     def limit(self, limit: int) -> "QuerySet[FOREIGN_MODEL]":
#         """Limit the number of related models."""
#         qs = self._build_query_set()
#         return qs.limit(limit)
    
#     async def add(self, obj: FOREIGN_MODEL, turn: Optional[int | Turn] = None, branch: Optional[int | Branch] = None) -> FOREIGN_MODEL:
#         """
#         Add a related model.
        
#         If the model has a _repo attribute, it will be saved with the appropriate branch.
#         """
#         if self.primary_instance is None:
#             raise ValueError("Instance is not set")
#         if not isinstance(obj, self.relation_field.foreign_cls):
#             raise ValueError("Object ({}) is not of type {}".format(obj.__class__.__name__, self.relation_field.foreign_cls.__name__))
#         # Set the relation field
#         setattr(obj, self.relation_field.foreign_key, self.primary_instance.primary_id)
        
#         if obj._is_versioned:
#             return await obj.save(turn=turn, branch=branch)
#         else:
#             return await obj.save()
#         # Save the object (branch will be determined by the model's repo)

    
#     @classmethod
#     def __get_pydantic_core_schema__(cls, source, handler):
#         def validate_custom(value, info):
#             if isinstance(value, cls):
#                 relation_model = get_one_to_many_relation_model(value)
#                 if issubclass(relation_model, Model):
#                     return value
#                 else:
#                     raise TypeError("Relation must be a Model")
#             else:
#                 raise TypeError("Invalid type for Relation; expected Relation instance")
#         return pydantic_core.core_schema.with_info_plain_validator_function(validate_custom)




# JUNCTION_MODEL = TypeVar("JUNCTION_MODEL", bound="Model")

# class ManyRelation(Generic[FOREIGN_MODEL, JUNCTION_MODEL], BaseRelation):
#     """
#     A relation between models.
    
#     This class provides methods for querying related models.
#     """        
#     relation_field: NSManyToManyRelationInfo
#     def __init__(self, namespace: Namespace, relation_field: NSManyToManyRelationInfo):
#         super().__init__(namespace)  
#         self.relation_field = relation_field      
            
#     def get_relation_key_params(self, obj: FOREIGN_MODEL, kwargs: dict[str, Any]):
#         params = {}
#         # params[self.relation_field.primary_key] = self.primary_instance.primary_id
#         # params[self.relation_field.foreign_key] = obj.primary_id
#         params[self.relation_field.junction_primary_key] = self.primary_instance.primary_id
#         params[self.relation_field.junction_foreign_key] = obj.primary_id
#         for key, value in kwargs.items():
#             params[key] = value
#         return params

#     # def _build_query_set(self):
#     #     """Build a query set for this relation."""
#     #     if not self.primary_instance:
#     #         raise ValueError("Instance is not set")
#     #     return self.primary_cls.query(partition_id=self.primary_instance.primary_id)
    
#     def _build_query_set(self):
#         """Build a query set for this relation."""
#         if not self.primary_instance:
#             raise ValueError("Instance is not set")
#         return self.relation_field.foreign_namespace.query(
#             partition_id=self.primary_instance.primary_id if self.is_context_model else None,
#             # joins=[{
#             #     "primary_table": self.relation_field.junction_table,
#             #     "primary_key": self.relation_field.junction_foreign_key,
#             #     "foreign_table": self.relation_field.foreign_table,
#             #     "foreign_key": self.relation_field.foreign_key,
#             # }],
#             select=[self.relation_field.foreign_namespace.select_fields()],
#             joins=[{
#                 "primary_table": self.relation_field.foreign_table,
#                 "primary_key": self.relation_field.foreign_key,
#                 "foreign_table": self.relation_field.junction_table,
#                 "foreign_key": self.relation_field.junction_foreign_key,
#             }],
#             filters={self.relation_field.junction_primary_key: self.primary_instance.primary_id},            
#         )
    
#     def all(self):
#         """Get all related models."""
#         return self._build_query_set()
    
#     def filter(self, filter_fn: Callable[[FOREIGN_MODEL], bool] | None = None, **kwargs) -> QuerySet[FOREIGN_MODEL]:
#         """Filter related models."""
#         qs = self._build_query_set()
#         return qs.filter(filter_fn=filter_fn,**kwargs)
    
#     def last(self) -> QuerySetSingleAdapter[FOREIGN_MODEL]:
#         """Get the last related model."""
#         qs = self._build_query_set()
#         return qs.last()
    
#     def tail(self, limit: int = 10) -> QuerySet[FOREIGN_MODEL]:
#         """Get the last N related models."""
#         qs = self._build_query_set()
#         return qs.tail(limit)
    
#     def first(self) -> QuerySetSingleAdapter[FOREIGN_MODEL]:
#         """Get the first related model."""
#         qs = self._build_query_set()
#         return qs.first()
    
#     def head(self, limit: int = 10) -> QuerySet[FOREIGN_MODEL]:
#         """Get the first N related models."""
#         qs = self._build_query_set()
#         return qs.head(limit)
    
#     def limit(self, limit: int) -> QuerySet[FOREIGN_MODEL]:
#         """Limit the number of related models."""
#         qs = self._build_query_set()
#         return qs.limit(limit)
        
    
#     async def add(self, obj: FOREIGN_MODEL, turn: Optional[int | Turn] = None, branch: Optional[int | Branch] = None, **kwargs) -> FOREIGN_MODEL:
#         """
#         Add a list of related models.
#         """
#         if self.primary_instance is None or self.relation_field.junction_cls is None:
#             raise ValueError("Instance or many_relation_cls is not set")

#         # obj = await super(ManyRelation, self).add(obj, turn, branch)        
#         if self.primary_cls._is_versioned:
#             obj = await obj.save(turn=turn, branch=branch)
#         else:
#             obj = await obj.save()
            
#         relation = self.relation_field.junction_cls(**self.get_relation_key_params(obj, kwargs))            
#         if self.primary_cls._is_versioned:
#             relation = await relation.save(turn=turn, branch=branch)
#         else:
#             relation = await relation.save()
#         # setattr(obj, self.relation_field.foreign_key, relation.primary_id)
#         # if obj.__class__._is_versioned:
#         #     await obj.save(turn=turn, branch=branch)
#         # else:
#         #     await obj.save()
#         return obj
    
    
#     # @classmethod
#     # def __get_pydantic_core_schema__(
#     #     cls, 
#     #     _source_type: Any, 
#     #     _handler: Callable[[Any], pydantic_core.core_schema.CoreSchema]
#     # ) -> pydantic_core.core_schema.CoreSchema:
#     #     from pydantic_core import core_schema
#     #     # Use a simple any schema since we're handling serialization ourselves
#     #     return core_schema.any_schema()
    
#     @classmethod
#     def __get_pydantic_core_schema__(cls, source, handler):
#         def validate_custom(value, info):
#             # print(value)
#             # print("---------------")
#             # print(info)
#             # print(source)
#             # print(handler)
#             if isinstance(value, cls):
#                 relation_model, target_model = get_many_to_many_relation_model(value)
#                 if issubclass(relation_model, Model) and issubclass(target_model, Model):
#                     return value
#                 else:
#                     raise TypeError("Relation must be a Model")
#             elif isinstance(value, list):
#                 for item in value:
#                     relation_model, target_model = get_many_to_many_relation_model(item)
#                     if not issubclass(relation_model, Model) or not issubclass(target_model, Model):
#                         raise TypeError("Relation must be a Model")
#                 return ManyRelation(cls.namespace, self.relation_field)
            
#             else:
#                 print(value)
#                 raise TypeError("Invalid type for Relation; expected Relation instance")
#         return pydantic_core.core_schema.with_info_plain_validator_function(validate_custom)




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

