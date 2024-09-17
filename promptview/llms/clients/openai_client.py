
import json
import os
from typing import List, Type

import openai
from promptview.llms.clients.base import BaseLlmClient
from promptview.llms.exceptions import LLMToolNotFound
from promptview.llms.messages import AIMessage, ActionCall, BaseMessage, validate_msgs
from promptview.llms.types import ToolChoice
from promptview.llms.utils.action_manager import Actions
from promptview.prompt.mvc import find_action
from promptview.utils.model_utils import schema_to_function
from pydantic import BaseModel


class OpenAiLlmClient(BaseLlmClient):


    def __init__(self, api_key=None):
        super().__init__(
            client = openai.AsyncClient(
                api_key=api_key or os.getenv("OPENAI_API_KEY")
            )
        )
        


    async def complete(
        self, 
        messages: List[BaseMessage], 
        actions: Actions | List[Type[BaseModel]]=[], 
        model="gpt-4o",
        tool_choice: ToolChoice | BaseModel | None = openai.NOT_GIVEN,
        run_id: str | None=None, 
        **kwargs
    ):
        if not isinstance(actions, Actions):
            actions = Actions(actions=actions)
        # tools = [schema_to_function(a) for a in actions] if actions else None
        tools = actions.to_openai()
        messages = [msg.to_openai() for msg in messages]
        if isinstance(tool_choice, BaseModel):
                tool_choice =  {"type": "function", "function": {"name": tool_choice.__class__.__name__}}            
        openai_completion = await self.client.chat.completions.create(
            messages=messages,
            tools=tools,
            model=model,
            tool_choice=tool_choice,
            **kwargs
        )
        return self.parse_output(openai_completion, actions)

    
    def parse_output(self, response, actions: Actions):
        output = response.choices[0].message
        tool_calls = []
        if output.tool_calls:
            for tool_call in output.tool_calls:
                action_instance = actions.from_openai(tool_call)
                # tool_calls.append({"id": tool_call.id, "action": action_instance})
                tool_calls.append(
                    ActionCall(
                        id=tool_call.id,
                        name=tool_call.function.name,
                        action=action_instance
                    ))
        ai_message = AIMessage(
            id=response.id,
            model=response.model,
            content=output.content,
            action_calls=tool_calls, 
            raw=response,
        )
        # for tc in tool_calls:
        #     ai_message.add_action(tc["id"], tc["action"])                
        return ai_message



# class OpenAiLlmClient(BaseLlmClient):


#     def __init__(self, api_key=None):
#         super().__init__(
#             client = openai.AsyncClient(
#                 api_key=api_key or os.getenv("OPENAI_API_KEY")
#             )
#         )

#     def preprocess(self, msgs):
#         return [msg.to_openai() for msg in validate_msgs(msgs)]
#         # return [msg.to_openai() for msg in msgs if msg.is_valid()]

#     async def complete(self, msgs, tools=None, run_id: str | None=None, **kwargs):
#         msgs = self.preprocess(msgs)
#         openai_completion = await self.client.chat.completions.create(
#             messages=msgs,
#             tools=tools,
#             **kwargs
#         )
#         return openai_completion
