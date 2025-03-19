from pydantic._internal._model_construction import ModelMetaclass
from pydantic import PrivateAttr, create_model, ConfigDict, BaseModel, Field
from typing import TYPE_CHECKING, Any, Callable, Dict, ForwardRef, Generic, List, Optional, Protocol, Self, Type, TypeVar, get_args, get_origin
from pydantic_core import PydanticUndefined
if TYPE_CHECKING:
    from promptview.model2.model import Model


def ModelField(
    default: Any = PydanticUndefined,
    *,
    foreign_key: bool = False,
    index: Optional[str] = None,
) -> Any:
    """Define a model field with ORM-specific metadata"""
    # Create extra metadata for the field
    extra = {}
    extra["index"] = index
    if foreign_key:
        extra["foreign_key"] = True
        default = None
    # Create the field with the extra metadata
    return Field(default, json_schema_extra=extra)


def KeyField(
    default: Any = None,
    # *,
    primary_key: bool = True,
    # **kwargs
) -> Any:
    """Define a key field with ORM-specific metadata"""
    # Create extra metadata for the field
    extra = {}
    extra["primary_key"] = primary_key
    
    # Create the field with the extra metadata
    return Field(default, json_schema_extra=extra)


def RefField(
    default: Any = None,
    *,
    key: str = "id",
    # **kwargs
) -> Any:
    """Define a reference field with ORM-specific metadata"""
    # Create extra metadata for the field
    extra = {}
    extra["key"] = key
    
    return Field(default, json_schema_extra=extra)

def RelationField(
    *,
    key: str | None = None,
    rel_keys: list[str] | None = None,
    on_delete: str = "CASCADE",
    on_update: str = "CASCADE",
    # **kwargs
) -> Any:
    """
    Define a relation field with ORM-specific metadata.
    
    Args:
        key: The name of the foreign key in the related model
        on_delete: The action to take when the referenced row is deleted
        on_update: The action to take when the referenced row is updated
    """
    # Create extra metadata for the field
    
    if not key and not rel_keys:
        raise ValueError("key or rel_keys must be provided")
    
    extra = {}
    extra["is_relation"] = True
    extra["key"] = key
    extra["rel_keys"] = rel_keys
    extra["on_delete"] = on_delete
    extra["on_update"] = on_update
    

    
        
    
    # Create the field with the extra metadata and make it optional
    return Field(json_schema_extra=extra)
    # return Field(json_schema_extra=extra, **kwargs)
    # return Field(json_schema_extra=extra, default_factory=lambda: None, **kwargs)


