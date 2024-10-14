
from typing import List, Type
from uuid import uuid4
from pydantic import BaseModel, Field
from promptview.llms.types import LLMToolNotFound
from promptview.llms.interpreter.messages import AIMessage, ActionCall
import xml.etree.ElementTree as ET

from promptview.utils.model_utils import is_list_model, unpack_list_model







class XmlOutputParser:
    
    # def __init__(self, xml_string, actions):
    #     self.root = ET.fromstring(xml_string)
    #     self.actions = actions
        
        
    def find_actions(self, actions, root, action_tag="action", param_tag="param"):
        action_calls = []        
        for action in root.findall(action_tag):
            action_cls = actions.get(action.attrib["name"])
            if not action_cls:
                raise LLMToolNotFound(action.attrib["name"])
            params = {param.attrib["name"]: param.text for param in action.findall(param_tag)}
            action_inst = action_cls(**params)
            action_calls.append(
                ActionCall(
                    id=f"tool_call_{uuid4()}", 
                    name=action.attrib["name"], 
                    action=action_inst
                )
            )
        return action_calls
        
    
    def find_list(self, root, tag, list_model_cls):
        fields = self.get_model_fields(list_model_cls)        
        list_roots = root.findall(tag)
        list_data = []
        for lr in list_roots:
            params = {k: lr.find(k).text for k in fields}
            list_data.append(list_model_cls(**params))
        return list_data
        
    def find_field(self, root, tag, field_info):
        if is_list_model(field_info.annotation):
            list_model = unpack_list_model(field_info.annotation)
            return self.find_list(root, tag, list_model)
        else: 
            res = root.find(tag)
            if res is None:
                return None
            return res.text

    def get_model_fields(self, model_cls):
        if not issubclass(model_cls, BaseModel):
            raise ValueError("model_cls must be a subclass of pydantic.BaseModel")
        parent_cls = model_cls.__bases__[0]
        if not issubclass(parent_cls, BaseModel):
            raise ValueError("model_cls Parent must be a subclass of pydantic.BaseModel")
        parent_fields = parent_cls.model_fields
        child_fields = model_cls.model_fields
        child_only_fields = {k: v for k, v in child_fields.items() if k not in parent_fields}
        return child_only_fields
    
    def parse(self, response: AIMessage, actions: List[BaseModel], ai_model_cls: Type[AIMessage]):
        if not issubclass(ai_model_cls, AIMessage):
            raise ValueError("model_cls must be a subclass of AIMessage")
        root = ET.fromstring(response.content)
        fields = self.get_model_fields(ai_model_cls)
        params = {k: self.find_field(root, k, f) for k, f in fields.items()}
        action_calls = {"action_calls": self.find_actions(actions, root)}
        try:
            output = ai_model_cls(
                id=response.id,
                content=response.content,
                model=response.model,
                raw=response.raw,
                usage=response.usage,
                **(params | action_calls)
            )
            # output = ai_model_cls(**(response.model_dump() | params | action_calls))
            return output
        except TypeError as e:
            print(params)
            print(action_calls)
            raise ValueError(f"Error parsing response: {e}")
        