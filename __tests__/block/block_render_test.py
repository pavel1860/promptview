import pytest

from promptview.prompt.block import block



def assert_render(block, target):
	render_out = block.render()
	print(render_out)
	assert render_out == target




def test_basic_render():
    
    with block() as r:
        r += "you should speak like a pirate"
    
    assert_render(r, "you should speak like a pirate")
    
    
    with block(title="Pirate") as r:
        r += "you should speak like a pirate"
    
    assert_render(r, "## Pirate\n  you should speak like a pirate")
    
    with block(title="Pirate", ttype="xml") as r:
        r += "you should speak like a pirate"
    
    assert_render(r, "<Pirate>\n  you should speak like a pirate\n</Pirate>")

