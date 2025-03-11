import pytest

from promptview.prompt import Block as blk



def assert_render(block, target):
	render_out = block.render()
	print(render_out)
	assert render_out == target




def test_basic_render():
    
    with blk() as r:
        r += "you should speak like a pirate"
    
    assert_render(r, "you should speak like a pirate")
    
    
    with blk("Pirate") as r:
        r += "you should speak like a pirate"
    
    assert_render(r, "# Pirate\nyou should speak like a pirate")
    
    with blk("Pirate", style=["xml"]) as r:
        r += "you should speak like a pirate"
    
    assert_render(r, "<Pirate>\nyou should speak like a pirate\n</Pirate>")




def test_wrapper_block():
    with blk(tags=["system"]) as b:
        b /= "you are a helpful assistant"
        with b("Task", tags=["task"]):
            b /= "this is task you need to complete"

    assert_render(b, "you are a helpful assistant\n# Task\nthis is task you need to complete")
    
    
    


def test_indentation():
    s = blk("""
        you are a helpful assistant
        Task:
            this is task you need to complete
        Rules:
        - you need to complete the task
        - you need to follow the rules
        Output Format:
        - you need to output the task
        - you need to output the rules
        - you need to output the output format
    """)
    target = """you are a helpful assistant
Task:
    this is task you need to complete
Rules:
- you need to complete the task
- you need to follow the rules
Output Format:
- you need to output the task
- you need to output the rules
- you need to output the output format"""

    assert_render(s, target)