import pytest
import pytest_asyncio
from promptview import view, prompt
from promptview.prompt.mvc import render_view



async def assert_basic_prompt(example_prompt, system_message, user_message, **kwargs):
    messages = await example_prompt(output_messages=True, **kwargs)
    for m in messages:
        print(f"-----{m.role}----")
        print(m.content)
    
    assert len(messages) == 2
    assert messages[0].content == system_message
    assert messages[1].content == user_message



@pytest.mark.asyncio
async def test_basic_view():
    @view()
    def example_view():
        return "this is an example view"

    out, _,_ = render_view(example_view())
    assert out == "this is an example view"
    
    
    
@pytest.mark.asyncio
async def test_basic_list_view():
    @view()
    def example_list_view():
        return [
            "this is an example view 1",
            "this is an example view 2",
            "this is an example view 3",
        ]

    out, _,_ = render_view(example_list_view())
    assert out == "this is an example view 1\nthis is an example view 2\nthis is an example view 3"
    

@pytest.mark.asyncio
async def test_basic_prompt():
    @prompt()
    def example_prompt():
        return "this is a test"

    messages = await example_prompt(output_messages=True)
    print(messages[0].content)
    assert messages[0].content == "this is a test"
    
    
@pytest.mark.asyncio
async def test_basic_prompt_list():
    @prompt()
    def example_prompt():
        return [
            "this is a test 1",
            "this is a test 2",
            "this is a test 3",
        ]

    messages = await example_prompt(output_messages=True)
    print(messages[0].content)
    assert messages[0].content == "this is a test 1\nthis is a test 2\nthis is a test 3"
    

@pytest.mark.asyncio
async def test_basic_propertie():
    @prompt(
        background="the is test background",
    )
    def example_prompt():
        return "this is a test"

    await assert_basic_prompt(example_prompt, "the is test background", "this is a test")
    

system_message = "this is a test background 1\nthis is a test background 2"

@pytest.mark.asyncio
async def test_basic_propertie_list():
    @prompt(
        background=[
            "this is a test background 1",
            "this is a test background 2",
        ]
    )
    def example_prompt():
        return "this is a test"
    await assert_basic_prompt(example_prompt, system_message, "this is a test")
    
    
    
@pytest.mark.asyncio
async def test_basic_propertie_function():
    def background_fn():
        return "the is test background"

    @prompt(
        background=background_fn
    )
    def example_prompt():
        return "this is a test"

    await assert_basic_prompt(example_prompt, "the is test background", "this is a test")
    
    

@pytest.mark.asyncio
async def test_basic_propertie_async_function():
    async def background_fn():
        return "the is test background"

    @prompt(
        background=background_fn
    )
    def example_prompt():
        return "this is a test"

    await assert_basic_prompt(example_prompt, "the is test background", "this is a test")
    
    

@pytest.mark.asyncio
async def test_basic_propertie_view():
    @view()
    def background_view():
        return "the is test background"


    @prompt(
        background=background_view
    )
    def example_prompt():
        return "this is a test"

    await assert_basic_prompt(example_prompt, "the is test background", "this is a test")
    
    
@pytest.mark.asyncio
async def test_basic_propertie_list_view():
    @view()
    def background_view():
        return [
            "this is a test background 1",
            "this is a test background 2",
        ]


    @prompt(
        background=background_view
    )
    def example_prompt():
        return "this is a test"

    await assert_basic_prompt(example_prompt, system_message, "this is a test")
    
    
    
@pytest.mark.asyncio
async def test_basic_propertie_function_list_view():    
    @view()
    def background_view(number):
        return f"this is a test background {number}"
            

    def background_fn():
        return [background_view(1), background_view(2)]


    @prompt(
        background=background_fn
    )
    def example_prompt():
        return "this is a test"

    await assert_basic_prompt(example_prompt, system_message, "this is a test")
    
    
@pytest.mark.asyncio
async def test_basic_propertie_replacement():
    @view()
    def background_view():
        return "this is a {value} background"
            
    def background_fn():
        return background_view()

    @prompt(
        background=background_fn
    )
    def example_prompt():
        return "this is a {value}"


    await assert_basic_prompt(example_prompt, "this is a test background", "this is a test", value="test")