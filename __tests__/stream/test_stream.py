import pytest
from typing import AsyncGenerator, Callable, Union, Optional, Any

from promptview.prompt.stream2 import AsyncStreamWrapper, stream  # Adjust the import

@pytest.mark.asyncio
async def test_basic_stream():
    async def gen():
        yield "A"
        yield "B"

    wrapper = AsyncStreamWrapper(gen(), accumulator=str)
    chunks = []
    async for chunk in wrapper:
        chunks.append(chunk)

    assert chunks == ["A", "B"]
    assert await AsyncStreamWrapper(gen(), accumulator=str) == "AB"

@pytest.mark.asyncio
async def test_nested_stream():
    async def inner():
        yield "X"
        yield "Y"

    async def outer():
        yield "Start"
        yield inner()
        yield "End"

    wrapper = AsyncStreamWrapper(outer(), accumulator=str)
    result = []
    async for token in wrapper:
        result.append(token)

    assert result == ["Start", "X", "Y", "End"]
    assert await AsyncStreamWrapper(outer(), accumulator=str) == "StartXYEnd"

@pytest.mark.asyncio
async def test_stream_events():
    async def gen():
        yield "A"
        yield "B"

    stream = AsyncStreamWrapper(gen(), accumulator=str)
    events = []
    async for event in stream.stream_events():
        events.append(event)

    assert events[0]["type"] == "stream_start"
    assert events[1]["type"] == "stream_delta"
    assert events[1]["value"] == "A"
    assert events[2]["type"] == "stream_delta"
    assert events[2]["value"] == "B"
    assert events[3]["type"] == "stream_end"
    assert events[3]["final_value"] == "AB"

@pytest.mark.asyncio
async def test_custom_accumulator():
    async def gen():
        yield "x"
        yield "y"

    class MyCollector:
        def __init__(self):
            self.data = []

        def append(self, x):
            self.data.append(x)

    stream = AsyncStreamWrapper(gen(), accumulator=MyCollector)
    result = await stream
    assert isinstance(result, MyCollector)
    assert result.data == ["x", "y"]

@pytest.mark.asyncio
async def test_stream_decorator():
    @stream(str)
    async def llm():
        yield "Hi"
        response = yield " there"
        yield response + "!"  # simulate return

    chunks = []
    async for token in llm():
        chunks.append(token)

    assert chunks == ["Hi", " there", "Hi there!"]
    assert await llm() == "Hi there!"

@pytest.mark.asyncio
async def test_stream_non_appendable_handling():
    async def gen():
        yield 42  # not appendable to str
        yield "B"

    stream = AsyncStreamWrapper(gen(), accumulator=str)
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)

    assert chunks == [42, "B"]
    assert await AsyncStreamWrapper(gen(), accumulator=str) == "B"
