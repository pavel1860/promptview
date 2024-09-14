from typing import Any

from pydantic import BaseModel
from promptview.llms.clients.base import BaseLlmClient
import os
import anthropic

from promptview.llms.exceptions import LLMToolNotFound
from promptview.llms.messages import BaseMessage, SystemMessage, AIMessage
from promptview.prompt.mvc import find_action
from promptview.utils.model_utils import schema_to_function
from promptview.llms.interpreter import LlmInterpreter
from typing import List

def convert_camel_to_snake(name):
    import re
    # Convert CamelCase to snake_case
    s1 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name)
    return s1.lower()


# schema = AttackAction.model_json_schema()

def actions_to_tools(actions: list[BaseModel]):
    tools = []
    for action in actions:
        schema = schema_to_function(action)['function']
        if hasattr(action,"_title"):
            name = action._title.default
        else:
            name = convert_camel_to_snake(action.__name__)
        tools.append({
            "name": name,
            "description": schema["description"],
            "input_schema": schema["parameters"],
        })
    return tools




class AnthropicLlmClient(BaseLlmClient):

    def __init__(self, api_key=None):
        super().__init__(
            # client = anthropic.Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY")),
            client = anthropic.AsyncAnthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY")),
        )

    async def complete(self, messages, actions=None, run_id: str | None=None, **kwargs):
        tools = actions_to_tools(actions) if actions else []
        system_message = None
        if isinstance(messages[0], SystemMessage):
            system_message = messages[0].content
            messages = messages[1:]
        antropic_messages = [m.to_antropic() for m in messages]
        anthropic_completion = await self.client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1000,
            temperature=0,
            system=system_message,
            messages=antropic_messages,
            tools=tools,
        )
        return self.parse_output(anthropic_completion, actions)
    
    def parse_output(self, response: anthropic.types.message.Message, actions: List[BaseModel])-> AIMessage:
        content = ''
        tool_calls = []
        for content_block in response.content:
            if content_block.type == 'text':
                content = content_block.text
            elif content_block.type == 'tool_use':
                action = find_action(content_block.name, actions)
                if not action:
                    raise LLMToolNotFound(content_block.name)
                tool_calls.append({"id": content_block.id, "action": action})
        ai_message = AIMessage(id=response.id, content=content, tool_calls=tool_calls)
        for tc in tool_calls:
            ai_message.add_action(tc["id"], tc["action"])
        return ai_message
