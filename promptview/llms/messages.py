from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, validator


class BaseMessage(BaseModel):
    id: Optional[str] = None
    content: str | None
    content_blocks: List[Dict[str, Any]] | None = None
    name: str | None = None
    is_example: Optional[bool] = False
    is_history: Optional[bool] = False
    is_output: Optional[bool] = False
    name: Optional[str] = None
    
    def is_valid(self):
        return self.content is not None

    def to_openai(self):
        oai_msg = {
            "role": self.role, # type: ignore
            "content": self.content,            
        }
        if self.name:
            oai_msg["name"] = self.name
        return oai_msg
    
    def to_antropic(self):
        return {
            "role": self.role,
            "content": self.content_blocks or self.content,
        }


class SystemMessage(BaseMessage):
    # role: str = Field("system", const=True)
    role: Literal["system"] = "system"


class HumanMessage(BaseMessage):
    # role: str = Field("user", const=True)
    role: Literal["user"] = "user"



class AIMessage(BaseMessage):
    model: str | None = None
    did_finish: Optional[bool] = True
    role: Literal["assistant"] = "assistant"
    run_id: Optional[str] = None
    tool_calls: Optional[List[Any]] = None
    # actions: Optional[List[BaseModel]] = []
    _iterator = -1
    _tool_responses = {}
    _tools = {}
    raw: Any = None


    def to_openai(self):
        if self.tool_calls:            
            oai_msg = {
                "role": self.role,
                "content": (self.content or '') + "\n".join([f"{t.function.name}\n{t.function.arguments}" for t in self.tool_calls])
            }
        else:
            oai_msg = {
                "role": self.role,
                "content": self.content,
            }
        if self._tool_responses:
            oai_msg['tool_calls'] = [r.tool_call for r in self._tool_responses.values()]
        if self.name:
            oai_msg["name"] = self.name
        return oai_msg
    
    def items(self):
        for tool_id, action in self._tools.items():
            yield tool_id, action
    
    @property
    def actions(self):
        return list(self._tools.values())
    
    @property
    def output(self):
        if not self.actions:
            return None
        return self.actions[0]
    
    @output.setter
    def output(self, value):
        self.actions = [value]
    
    def is_valid(self):
        if self.content is not None:
            return True 
        elif self._tool_responses:
            return True
        return False
    
    def _add_tool_response(self, response: "ActionMessage"):
        self._tool_responses[response.id] = response
    
    def add_action_output(self, tool_id: str, output: BaseModel | str | dict):
        self._tool_responses[tool_id] = output
        
    def add_action(self, tool_id: str, action: BaseModel):
        self._tools[tool_id] = action

    # def to_openai(self):
    #     oai_msg = {"role": self.role}                
    #     if self.content:
    #         oai_msg["content"] = self.content
    #     # if self.tool_calls:
    #     #     responded_tools = [t for t in self.tool_calls if t.id in self._tool_responses]   
    #     #     if responded_tools:
    #     #         oai_msg['tool_calls'] = responded_tools
    #     if self._tool_responses:
    #         oai_msg['tool_calls'] = [r.tool_call for r in self._tool_responses.values()]
    #     return oai_msg
    
    # def __iter__(self):
    #     self._iterator = -1
    #     return self
    
    # def __next__(self):
    #     if self._iterator == -1:
    #         self._iterator += 1
    #         if self.content:                
    #             return "response", self.content            
    #     if self._iterator >= len(self.actions):
    #         raise StopIteration
    #     return self.tool_calls[self._iterator].id, self.actions[self._iterator]
    
    
  
class ActionMessage(BaseMessage):
    role: Literal["tool"] = "tool"  
    
    # @property
    # def id(self):
    #     return self.tool_call.id
    
    def to_openai(self):
        return {
            "tool_call_id": self.tool_call.id,
            "role": "tool",
            "name": self.name,
            "content": self.content
        }
        



ChatMessageType = Union[SystemMessage, HumanMessage, AIMessage]


def validate_msgs(msgs: List[BaseMessage]) -> List[BaseMessage]:
    ai_messages = {}

    validated_msgs = []
    for msg in msgs:
        if isinstance(msg, AIMessage):
            if msg.tool_calls:
                ai_messages[msg.tool_calls[0].id] = msg
            else:
                validated_msgs.append(msg)
        elif isinstance(msg, ActionMessage):
            ai_msg = ai_messages.get(msg.tool_call.id, None)
            if not ai_msg:
                continue
            validated_msgs += [ai_msg, msg]
            # validated_msgs.append((ai_msg, msg))
        else:
            validated_msgs.append(msg)
    return validated_msgs

