from enum import Enum
import inspect
import json
from typing import Any, Literal, Optional, Union, get_args, get_origin
from pydantic import BaseModel, create_model


class Config:
    arbitrary_types_allowed = True



def is_list_model(pydantic_model):
    return get_origin(pydantic_model) == list

def unpack_list_model(pydantic_model):
    return get_args(pydantic_model)[0]



def remove_a_key(d, remove_key):
    if isinstance(d, dict):
        for key in list(d.keys()):
            if key == remove_key:
                del d[key]
            else:
                remove_a_key(d[key], remove_key)

def schema_to_function(schema: Any):
    assert schema.__doc__, f"{schema.__name__} is missing a docstring."
    assert (
        "title" not in schema.__fields__.keys()
    ), "`title` is a reserved keyword and cannot be used as a field name."
    schema_dict = schema.model_json_schema()
    remove_a_key(schema_dict, "title")

    return {
        "type": "function",
        "function": {
            "name": schema.__name__,
            "description": schema.__doc__,
            "parameters": schema_dict,
        }
    }


def make_optional(model: BaseModel) -> BaseModel:
    optional_fields = {k: (Optional[v], None) for k, v in model.__annotations__.items()}
    return create_model(
        model.__name__, 
        **optional_fields, 
        __config__=Config
    )




def get_model_fields(model_instance, model_class):
    fields = {field: getattr(model_instance, field) for field in model_class.__fields__.keys()}
    return model_class(**fields)



# def iterate_class_fields(cls_, sub_cls_filter=None, exclude=False):
#     for field, info in cls_.__fields__.items():
#         if sub_cls_filter is not None and (not inspect.isclass(info.annotation) or not issubclass(info.annotation, sub_cls_filter)):
#             continue
#         yield field, info


# def iterate_class_fields(cls_, sub_cls_filter=None, exclude=False):
#     for field, info in cls_.__fields__.items():
#         if sub_cls_filter is not None:
#             if not exclude and (inspect.isclass(info.annotation) and issubclass(info.annotation, sub_cls_filter)):
#                 yield field, info
#             if exclude and (not inspect.isclass(info.annotation) or not issubclass(info.annotation, sub_cls_filter)):
#                 yield field, info                
#             continue
#         yield field, info



def iterate_class_fields(cls_, sub_cls_filter=None, exclude=False):

    def _issubclass(cls_, sub_cls_filter):
        if type(sub_cls_filter) == list:
            return any([issubclass(cls_, sub_cls) for sub_cls in sub_cls_filter])
        return issubclass(cls_, sub_cls_filter)

    for field, info in cls_.__fields__.items():
        if sub_cls_filter is not None:
            if not exclude and (inspect.isclass(info.annotation) and _issubclass(info.annotation, sub_cls_filter)):
                yield field, info
            if exclude and (not inspect.isclass(info.annotation) or not _issubclass(info.annotation, sub_cls_filter)):
                yield field, info                
            continue
        yield field, info




def serialize_class(cls_: Any):
    output_type = "object"
    if is_list_model(cls_):
        output_type = "array"
        output_class = unpack_list_model(cls_)
    else:
        output_class = cls_
    if hasattr(output_class, 'model_json_schema'):
        schema = output_class.model_json_schema()
        version = 'v2'
    else:
        schema = schema_to_function(output_class)
        version = 'v1'
    return {
        "type": output_type,
        "schema": schema,
        "pydantic_version": version
    }





def describe_enum(enum_cls: Enum, delimiter: str = ", ") -> str:
    return delimiter.join([v.value for v in enum_cls])

def describe_literal(literal, delimiter="|"):
    args = get_args(literal)
    return delimiter.join(args)

def is_union(obj):
    orig = get_origin(obj)
    if orig and orig.__name__ == "UnionType":
        return True
    return hasattr(obj, "__origin__") and obj.__origin__ == Union


def get_type(arg, delimiter="|"):
    if isinstance(arg, type):
        if issubclass(arg, Enum):
            return describe_enum(arg, delimiter)
    elif get_origin(arg) is Literal:
        return describe_literal(arg, delimiter)
    return arg.__name__


def get_union_args(field_info, delimiter="|"):    
    union_args = get_args(field_info.annotation)
    type_args = []
    for arg in union_args:
        if arg == type(None):
            is_optional = True
        else:
            type_args.append(get_type(arg, delimiter))
    if is_optional:
        type_args.append("None")
    return delimiter.join(type_args)


def get_list_args(field_info, delimiter="|"):
    args = get_args(field_info.annotation)[0]
    return f"List[{stringify_field_info(args, delimiter)}]"

def get_field_info_origin(field_info, delimiter="|"):
    field_origin = get_origin(field_info.annotation)
    if field_origin == list:
        return get_list_args(field_info, delimiter)    
    else:
        return get_union_args(field_info.annotation)


def stringify_field_info(field_info, delimiter="|"):
    field_type = field_info.annotation if hasattr(field_info, "annotation") else field_info
    field_origin = get_origin(field_type)
    if field_origin == list:
        return get_list_args(field_info, delimiter)
    elif is_union(field_type):
        return get_union_args(field_info, delimiter)
    else:
        return get_type(field_type, delimiter)




