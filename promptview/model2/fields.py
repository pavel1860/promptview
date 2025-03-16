from pydantic._internal._model_construction import ModelMetaclass
from pydantic import PrivateAttr, create_model, ConfigDict, BaseModel, Field
from typing import Any, Callable, Dict, ForwardRef, Generic, List, Optional, Protocol, Self, Type, TypeVar, get_args, get_origin
from pydantic_core import PydanticUndefined



def ModelField(
    default: Any = PydanticUndefined,
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
    default: Any = PydanticUndefined,
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


def RelationField(
    *,
    key: str,
    on_delete: str = "CASCADE",
    on_update: str = "CASCADE",
    **kwargs
) -> Any:
    """
    Define a relation field with ORM-specific metadata.
    
    Args:
        key: The name of the foreign key in the related model
        on_delete: The action to take when the referenced row is deleted
        on_update: The action to take when the referenced row is updated
    """
    # Create extra metadata for the field
    extra = kwargs.pop("json_schema_extra", {}) or {}
    extra["is_relation"] = True
    extra["key"] = key
    extra["on_delete"] = on_delete
    extra["on_update"] = on_update
    
    # Create the field with the extra metadata and make it optional
    return Field(json_schema_extra=extra)
    # return Field(json_schema_extra=extra, **kwargs)
    # return Field(json_schema_extra=extra, default_factory=lambda: None, **kwargs)


