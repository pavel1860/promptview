import pytest
import pytest_asyncio

from promptview.block import Block
from promptview.block.block7 import BlockList
from promptview.llms.openai_llm3 import OpenAiLLM









@pytest_asyncio.fixture()
async def test_basic_parser():
    with Block() as prompt:
        with prompt(role="system") as s:
            s /= "you are a pirate"
            s /= "you should answer in pirate language"
        
            with s.response_schema() as schema:
                with schema.field("output", str) as res:
                    with res.field("thought", str) as t:
                        t /= "internal step by step thinking process goes here"
                    with res.field("answer", str) as a:
                        a /= "your answer to the user goes here"
        
        
        with prompt(role="user") as u:
            u /= "Hello"
            
    llm = OpenAiLLM()
    stream = llm.stream(BlockList([prompt])).load("pirate_attrs", "__tests__/data").parse(schema)
    output = []
    async for c in stream:
        print(c)
        output.append(c)
