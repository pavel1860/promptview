import uuid
from pydantic._internal._model_construction import ModelMetaclass
from pydantic import PrivateAttr, create_model, ConfigDict, BaseModel, Field
from pydantic.fields import _Unset, AliasPath, AliasChoices, FieldInfo, JsonDict, Unpack, _EmptyKwargs, Deprecated # type: ignore
from typing import TYPE_CHECKING, Any, Callable, Dict, ForwardRef, Generic, List, Literal, Optional, Protocol, Self, Type, TypeVar, get_args, get_origin
from pydantic_core import PydanticUndefined

from promptview.algebra.vectors.base_vectorizer import BaseVectorizer
from promptview.algebra.vectors.empty_vectorizer import EmptyVectorizer

if TYPE_CHECKING:
    from promptview.model2.model import Model







def ModelField(
    default: Any = PydanticUndefined,
    *,
    foreign_key: bool = False,
    index: Optional[str] = None,
    default_factory: Callable[[], Any] | None = _Unset,
    is_default_temporal: bool = False,
    db_type: str | None = None,
    description: str | None = _Unset,
) -> Any:
    """Define a model field with ORM-specific metadata"""
    # Create extra metadata for the field
    extra = {}
    extra["is_model_field"] = True
    extra["is_default_temporal"] = is_default_temporal
    extra["index"] = index    
    if db_type:
        extra["db_type"] = db_type
    if foreign_key:
        extra["foreign_key"] = True
        default = None
    # Create the field with the extra metadata
    return Field(
        default,
        default_factory=default_factory,
        json_schema_extra=extra,
        description=description,
    )


def KeyField(
    default: Any = None,
    # *,
    primary_key: bool = False,
    type: Literal["int", "uuid"] = "int",
    description: str | None = _Unset,
    # **kwargs
) -> Any:
    """Define a key field with ORM-specific metadata"""
    # Create extra metadata for the field
    extra = {}
    extra["is_model_field"] = True
    extra["primary_key"] = primary_key
    extra["type"] = type
    extra["is_key"] = True
    # if type == "uuid" and not primary_key:
        # return Field(default_factory=lambda: uuid.uuid4(), json_schema_extra=extra, description=description)
    # Create the field with the extra metadata
    return Field(default, json_schema_extra=extra, description=description)


def RefField(
    default: Any = None,
    *,
    key: str = "id",
    description: str | None = _Unset,
    # **kwargs
) -> Any:
    """Define a reference field with ORM-specific metadata"""
    # Create extra metadata for the field
    extra = {}
    extra["is_model_field"] = True
    extra["key"] = key
    
    return Field(default, json_schema_extra=extra, description=description)

def RelationField(
    default: Any = None,
    *,
    primary_key: str | None = None,
    foreign_key: str | None = None,
    junction_keys: list[str] | None = None,
    junction_model: "Type[Model] | None" = None,
    on_delete: str = "CASCADE",
    on_update: str = "CASCADE",
    description: str | None = _Unset,
    # **kwargs
) -> Any:
    """
    Define a relation field with ORM-specific metadata.
    
    Args:
        primary_key: The name of the primary key in the related model
        foreign_key: The name of the foreign key in the related model
        junction_keys: The names of the junction keys in the related model
        on_delete: The action to take when the referenced row is deleted
        on_update: The action to take when the referenced row is updated
    """
    # Create extra metadata for the field
    from promptview.model2.relation import Relation
    if not primary_key and not foreign_key and not junction_keys:
        raise ValueError("primary_key or foreign_key or junction_keys must be provided")
    if not default:
        # default = []
        default = Relation()
        # default = EmptyRelation()
    
    extra = {}
    extra["is_model_field"] = True
    extra["is_relation"] = True
    extra["primary_key"] = primary_key
    extra["foreign_key"] = foreign_key
    extra["junction_keys"] = junction_keys
    extra["on_delete"] = on_delete
    extra["on_update"] = on_update
    extra["junction_model"] = junction_model
    
    if junction_keys:
        if not primary_key or not foreign_key:
            raise ValueError("primary_key and foreign_key must be provided if junction_keys are provided")
        if not junction_model:
            raise ValueError("junction_model must be provided if junction_keys are provided")
        # extra["type"] = "many_to_many"
    # elif foreign_key:
    #     extra["type"] = "many_to_one"
    
    # Create the field with the extra metadata and make it optional
    return Field(default, json_schema_extra=extra, description=description)
    # return Field(json_schema_extra=extra, **kwargs)
    # return Field(json_schema_extra=extra, default_factory=lambda: None, **kwargs)





def VectorField(
    default: Any = None,
    *,
    dimension: int | None = None,
    vectorizer: Type[BaseVectorizer] | None = None,
    distance: Literal["cosine", "euclid"] = "cosine",
    description: str | None = _Unset,
) -> Any:
    extra = {}
    
    # if vectorizer is None:
    #     vectorizer = EmptyVectorizer
    #     dimension = 300
    # else:
    #     if not dimension:
    #         dimension = vectorizer.dimension
    extra["is_model_field"] = True
    extra["dimension"] = dimension
    extra["is_vector"] = True    
    extra["vectorizer"] = vectorizer
    extra["distance"] = distance 
    return Field(default, json_schema_extra=extra, description=description)




