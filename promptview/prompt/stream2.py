import inspect
from typing import Any, AsyncGenerator, Union, AsyncIterator

class GeneratorFrame:
    def __init__(self, agen: AsyncGenerator):
        self.agen = agen
        self.started = False

    async def advance(self, value: Any):
        if not self.started:
            self.started = True
            return await self.agen.__anext__()
        else:
            return await self.agen.asend(value)

class AsyncStreamWrapper:
    def __init__(self, agen: Union[AsyncGenerator, Any]):
        self._stack = []
        self._initial_gen = agen
        self._accumulator = ""

    def __aiter__(self) -> AsyncIterator[str]:
        self._stack = [self._wrap(self._initial_gen)]
        return self

    async def __anext__(self) -> str:
        while self._stack:
            current = self._stack[-1]
            try:
                value = await current.advance(self._accumulator)

                if inspect.isasyncgen(value):
                    self._stack.append(self._wrap(value))
                    continue

                if isinstance(value, str):
                    self._accumulator += value

                return value

            except StopAsyncIteration as e:
                self._stack.pop()
                if hasattr(e, "value") and e.value is not None:
                    self._accumulator = e.value

        raise StopAsyncIteration

    def _wrap(self, value: Any) -> GeneratorFrame:
        if inspect.isasyncgenfunction(value):
            value = value()
        if not inspect.isasyncgen(value):
            raise TypeError(f"{value} is not an async generator")
        return GeneratorFrame(value)

    async def stream_events(self):
        """Yields structured events: start, deltas, and end."""
        yield {"type": "stream_start"}

        async for chunk in self:
            yield {"type": "stream_delta", "value": chunk}

        yield {"type": "stream_end", "final_value": self._accumulator}
