from pydantic._internal._model_construction import ModelMetaclass
from pydantic import PrivateAttr, create_model, ConfigDict, BaseModel, Field
from typing import Any, Callable, Dict, ForwardRef, Generic, List, Optional, Protocol, Self, Type, TypeVar, get_args, get_origin


def ModelField(
    default: Any = None,
    *,
    index: Optional[str] = None,
    **kwargs
) -> Any:
    """Define a model field with ORM-specific metadata"""
    # Create extra metadata for the field
    extra = kwargs.pop("json_schema_extra", {}) or {}
    extra["index"] = index
    
    # Create the field with the extra metadata
    return Field(default, json_schema_extra=extra, **kwargs)


def KeyField(
    default: Any = None,
    *,
    primary_key: bool = True,
    **kwargs
) -> Any:
    """Define a key field with ORM-specific metadata"""
    # Create extra metadata for the field
    extra = kwargs.pop("json_schema_extra", {}) or {}
    extra["primary_key"] = primary_key
    
    # Create the field with the extra metadata
    return Field(default, json_schema_extra=extra, **kwargs)


class ModelMeta(ModelMetaclass, type):
    """Metaclass for Model"""
    
    def __new__(cls, name, bases, dct):
        """Create a new Model class"""
        # Use the standard Pydantic metaclass to create the class
        cls_obj = super().__new__(cls, name, bases, dct)
        # Initialize the fields dictionary
        cls_obj._fields = {}
        # The decorator will handle the ORM functionality
        return cls_obj


class Model(BaseModel, metaclass=ModelMeta):
    """Base class for all models
    
    This class is a simple Pydantic model with a custom metaclass.
    The ORM functionality will be added by the decorator.
    """
    # Namespace reference - will be set by the decorator
    _namespace_name: str = PrivateAttr(default=None)


class KeyModel(Model):
    """Model with a primary key
    
    This class adds an ID field to the model.
    """
    id: int = KeyField(default=None, primary_key=True)


class VectorModel(Model):
    """Model with vector embedding support"""
    pass


class VersionedModel(Model):
    """Model with versioning support"""
    pass
    pass

