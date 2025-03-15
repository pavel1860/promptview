from typing import Any, Dict, Optional, Type, TypeVar, Callable, cast
from pydantic import BaseModel, Field, PrivateAttr
from pydantic.config import JsonDict
from pydantic._internal._model_construction import ModelMetaclass

from promptview.model2.namespace_manager import NamespaceManager
from promptview.model2.base_namespace import DatabaseType
from promptview.model2.versioning import Branch

T = TypeVar('T', bound=BaseModel)


def get_dct_private_attributes(dct: dict[str, Any], key: str, default: Any=None) -> Any:
    """Get the private attributes of a class"""
    res = dct['__private_attributes__'].get(key)
    if hasattr(res, "default"):
        res = res.default
    if not res:
        return default    
    return res


class ModelMeta(ModelMetaclass, type):
    """Metaclass for Model
    
    This metaclass handles the registration of models with the namespace manager
    and the processing of fields.
    """
    
    def __new__(cls, name, bases, dct):
        # Use the standard Pydantic metaclass to create the class
        cls_obj = super().__new__(cls, name, bases, dct)
        
        # Skip processing for the base Model class
        if name == "Model" or name == "RepoModel" or name == "ArtifactModel":
            return cls_obj
        
        # Get model name and namespace
        model_name = name
        namespace_name = get_dct_private_attributes(dct, "_namespace_name", f"{model_name.lower()}s")
        db_type = get_dct_private_attributes(dct, "_db_type", "postgres")
        is_versioned = get_dct_private_attributes(dct, "_is_versioned", False)
        
        # Build namespace
        ns = NamespaceManager.build_namespace(namespace_name, db_type, is_versioned)
        
        # Process fields
        for field_name, field_info in cls_obj.model_fields.items():
            # Skip fields without a type annotation
            if field_info.annotation is None:
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
            
            # Add field to namespace
            ns.add_field(field_name, field_info.annotation, extra)
        
        # Set namespace name on the class
        cls_obj._namespace_name = namespace_name
        
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
    
    @classmethod
    def get_namespace_name(cls) -> str:
        """Get the namespace name for this model"""
        return cls._namespace_name
    
    @classmethod
    async def initialize(cls):
        """Initialize the model (create table)"""
        ns = NamespaceManager.get_namespace(cls.get_namespace_name())
        await ns.create_namespace()
    
    async def save(self, branch: Optional[int | Branch] = None):
        """
        Save the model instance to the database
        
        Args:
            branch: Optional branch ID to save to
        """
        
        
        if branch:
            if not self._is_versioned:
                raise ValueError("Model is not versioned but branch is provided")
            if isinstance(branch, Branch):
                branch = branch.id
        ns = NamespaceManager.get_namespace(self.__class__.get_namespace_name())
        data = self.model_dump()
        result = await ns.save(data, branch)
        # Update instance with returned data (e.g., ID)
        for key, value in result.items():
            setattr(self, key, value)
        return self
    
    @classmethod
    async def get(cls, id: Any):
        """Get a model instance by ID"""
        ns = NamespaceManager.get_namespace(cls.get_namespace_name())
        data = await ns.get(id)
        return cls(**data) if data else None
    
    @classmethod
    def query(cls, branch: Optional[int | Branch] = None):
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
        ns = NamespaceManager.get_namespace(cls.get_namespace_name())
        return ns.query(branch)


# No need for the ModelFactory class anymore




class ArtifactModel(Model):
    branch_id: int = Field(default=None)
    turn_id: int = Field(default=None)



class RepoModel(Model):
    main_branch_id: int = Field(default=None)
    
    
    
    
    
    
    
