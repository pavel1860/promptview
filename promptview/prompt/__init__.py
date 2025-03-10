from .block4 import BaseBlock
from .block_ctx import Block
# from .str_block import BaseBlock, StrBlock, DictBlock
from .base_prompt3 import prompt, Prompt
from .agent import Agent, agent



# Block.register(type(None), BaseBlock)
# Block.register(str, StrBlock)
# Block.register(dict, DictBlock)



__all__ = [
    "Block",
    "BaseBlock",
    # "StrBlock",
    # "DictBlock",
    "prompt",
    "Prompt",
    "Agent",
    "agent",
]