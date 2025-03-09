import datetime as dt
from enum import Enum
import inspect
from typing import Any
import typing
from pydantic import BaseModel, Field
from pydantic_core import PydanticUndefined
from pydantic import types
from pydantic.fields import _Unset, AliasPath, AliasChoices, FieldInfo, JsonDict, Unpack, _EmptyKwargs, Deprecated
import typing_extensions
import annotated_types

from typing_extensions import Literal, TypeAlias, Unpack, deprecated






class IndexType(Enum):
    Keyword = "keyword"
    Integer = "integer"
    Float = "float"
    Bool = "bool"
    Geo = "geo"
    Datetime = "datetime"
    Text = "text"
    Uuid = "uuid"



class VectorSpaceMetrics:
    """Supported metrics for vector similarity"""
    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    MANHATTAN = "manhattan"








def ModelField(
    default: Any = PydanticUndefined,
    *,    
    partition: dict[str, str] | None = None,
    index: IndexType | None = None,
    is_tenent: bool = False,
    auto_now_add: bool = False,
    auto_now: bool = False,
    default_factory: typing.Callable[[], Any] | None = _Unset,
    alias: str | None = _Unset,
    alias_priority: int | None = _Unset,
    validation_alias: str | AliasPath | AliasChoices | None = _Unset,
    serialization_alias: str | None = _Unset,
    title: str | None = _Unset,
    field_title_generator: typing_extensions.Callable[[str, FieldInfo], str] | None = _Unset,
    description: str | None = _Unset,
    examples: list[Any] | None = _Unset,
    exclude: bool | None = _Unset,
    discriminator: str | types.Discriminator | None = _Unset,
    deprecated: Deprecated | str | bool | None = _Unset,
    json_schema_extra: JsonDict | typing.Callable[[JsonDict], None] | None = _Unset,
    frozen: bool | None = _Unset,
    validate_default: bool | None = _Unset,
    repr: bool = _Unset,
    init: bool | None = _Unset,
    init_var: bool | None = _Unset,
    kw_only: bool | None = _Unset,
    pattern: str | typing.Pattern[str] | None = _Unset,
    strict: bool | None = _Unset,
    coerce_numbers_to_str: bool | None = _Unset,
    gt: annotated_types.SupportsGt | None = _Unset,
    ge: annotated_types.SupportsGe | None = _Unset,
    lt: annotated_types.SupportsLt | None = _Unset,
    le: annotated_types.SupportsLe | None = _Unset,
    multiple_of: float | None = _Unset,
    allow_inf_nan: bool | None = _Unset,
    max_digits: int | None = _Unset,
    decimal_places: int | None = _Unset,
    min_length: int | None = _Unset,
    max_length: int | None = _Unset,
    union_mode: Literal['smart', 'left_to_right'] = _Unset,
    fail_fast: bool | None = _Unset,
    **extra: Unpack[_EmptyKwargs],
):
    """
    par
    """
    if auto_now_add and auto_now:
        raise ValueError("auto_now_add and auto_now cannot be True at the same time")
    if auto_now_add:
        if default_factory != _Unset:
            raise ValueError("default_factory cannot be set when auto_now_add is True")
        default_factory = dt.datetime.now
        if index is None:
            index = IndexType.Datetime
        elif index != IndexType.Datetime:
            raise ValueError("auto_now_add must have index type of Datetime")
    
    if auto_now:
        if default_factory != _Unset:
            raise ValueError("default_factory cannot be set when auto_now is True")
        default_factory = dt.datetime.now
        if index is None:
            index = IndexType.Datetime
        elif index != IndexType.Datetime:
            raise ValueError("auto_now_add must have index type of Datetime")
        
    json_schema_extra={
            "partition": partition,
            "is_relation": True if partition else False,
            "index": index.value if index else None,
            "is_tenent": is_tenent,
            "auto_now_add": auto_now_add,
            "auto_now": auto_now
        }
    
    return Field(
        default,
        default_factory=default_factory,
        alias=alias,
        alias_priority=alias_priority,
        validation_alias=validation_alias,
        serialization_alias=serialization_alias,
        title=title,
        field_title_generator=field_title_generator,
        description=description,
        examples=examples,
        exclude=exclude,
        discriminator=discriminator,
        deprecated=deprecated,
        json_schema_extra=json_schema_extra,
        frozen=frozen,
        validate_default=validate_default,
        repr=repr,
        init=init,
        init_var=init_var,
        kw_only=kw_only,
        pattern=pattern,
        strict=strict,
        coerce_numbers_to_str=coerce_numbers_to_str,
        gt=gt,
        ge=ge,
        lt=lt,
        le=le,
        multiple_of=multiple_of,
        allow_inf_nan=allow_inf_nan,
        max_digits=max_digits,
        decimal_places=decimal_places,
        min_length=min_length,
        max_length=max_length,
        union_mode=union_mode,
        fail_fast=fail_fast,
        **extra        
    )







def get_field_extra(info):
    if hasattr(info, 'json_schema_extra'):
        return info.json_schema_extra
    elif hasattr(info, 'field_info'): # check if pydantic v1
        return info.field_info.extra
    return {}



def interate_fields(obj):
    if hasattr(obj, "__fields__"):
        for field, info in obj.__fields__.items():
            if isinstance(info, FieldInfo):
                yield field, info
    else:
        for field, info in obj.items():
            if isinstance(info, FieldInfo):
                yield field, info

def get_model_indices(cls_, prefix=""):
    indexs_to_create = []
    for field, info in interate_fields(cls_):
        if inspect.isclass(info.annotation) and issubclass(info.annotation, BaseModel):
            indexs_to_create += get_model_indices(info.annotation, prefix=prefix+field+".")
        extra = get_field_extra(info)        
        if extra:
            if "index" in extra:
                # print("found index:", field, extra["index"])
                indexs_to_create.append({
                    "field": prefix+field,
                    "schema": extra["index"]
                })
    return indexs_to_create




# def AssetField(
#     *args,
#     partition: str | None = None,
#     index: IndexType | None = None,
#     is_tenent: bool = False,
#     auto_now_add: bool = False,
#     auto_now: bool = False,
#     **kwargs
# ):
#     if auto_now_add and auto_now:
#         raise ValueError("auto_now_add and auto_now cannot be True at the same time")
#     if auto_now_add:
#         if "default_factory" in kwargs:
#             raise ValueError("default_factory cannot be set when auto_now_add is True")
#         kwargs["default_factory"] = dt.datetime.now
    
#     if auto_now:
#         if "default_factory" in kwargs:
#             raise ValueError("default_factory cannot be set when auto_now is True")
#         kwargs["default_factory"] = dt.datetime.now
    
#     return Field(
#         *args,
#         json_schema_extra={
#             "partition": partition,
#             "index": index.value if index else None,
#             "is_tenent": is_tenent,
#             "auto_now_add": auto_now_add,
#             "auto_now": auto_now
#         },
#         **kwargs
#     )






