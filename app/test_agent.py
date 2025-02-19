
from promptview.prompt.base_prompt3 import prompt
from promptview.llms.openai_llm2 import OpenAiLLM
from app.test_models import Message
from promptview.prompt.depends import Depends
from promptview.prompt.block2 import block as b



@prompt()
async def chat_prompt(message: Message, llm: OpenAiLLM = Depends(OpenAiLLM)):
    
    with b("""
    you should act like a pirate.       
    your name is Jack Sparrow.
    """, role="system") as sm:
        with b.title("Task"):
            b("your task is to learn about the user.")
        
    with b.title("User Message", role="user") as um:
        b(message.content)
    
    res = await llm([sm, um]).generate()
    return res




async def run_agent(message: Message):
    res = await chat_prompt(message=message)
    return Message(content=str(res), role="assistant")



