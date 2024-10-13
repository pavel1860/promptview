from enum import Enum
import inspect
from pydantic import BaseModel
from promptview.prompt.view_block import view
from typing import Optional, Union, get_type_hints, get_origin, get_args, Type, Literal

from promptview.utils.model_utils import describe_enum, stringify_field_info




@view()
def action_field_view(field_name: str, field_info):
    try:                        
        # return f"{field_name} ({get_field_info_origin(field_info)}): {field_info.description}"
        return f"""{field_name} ({stringify_field_info(field_info, "|")}): {field_info.description}"""
    except AttributeError:
        raise ValueError(f"Invalid field_info: {field_info}")
    


@view(title="Parameters", bullet="bullet")
def action_param_view(action: BaseModel):    
    return [
        action_field_view(field_name, field_info)
        for field_name, field_info in
        action.model_fields.items()
    ]

@view(indent=1)
def action_sub_view(action: BaseModel):
    return (
        f"Purpose: " + action.__doc__,
        action_param_view(action)
    )
    
@view()
def action_view(action_name: str, action: BaseModel):
    return (
        action_name,
        action_sub_view(action)        
    )

@view(
    title="You have the following actions available",
    bullet="number",
)
def system_action_view(actions):
    return [action_view(action_name, action) for action_name, action in actions]