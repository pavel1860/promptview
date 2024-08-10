import inspect
import json
from typing import Any, Optional

from promptview.llms.utils.completion_parsing import (is_list_model,
                                                    unpack_list_model)
from pydantic import BaseModel, create_model


class Config:
    arbitrary_types_allowed = True



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
