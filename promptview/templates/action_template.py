from pydantic import BaseModel
from promptview.prompt.mvc import view

@view()
def action_field_view(field_name, field_info):
    return f"{field_name} ({field_info.annotation.__name__}): {field_info.description}"
    


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