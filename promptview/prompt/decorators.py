from functools import wraps
import inspect
from typing import Any, AsyncGenerator, Callable, Iterable, Literal, ParamSpec, Protocol, Union, AsyncIterator, Optional, Generic
from typing_extensions import TypeVar

from promptview.prompt.events import Event
from promptview.prompt.flow_components import PipeController, StreamController
from promptview.prompt.injector import InjectableFunction, resolve_dependencies





CHUNK = TypeVar("CHUNK")
StreamFilter = Literal["pass_events", "all", "self"]


class SupportsExtend(Protocol[CHUNK]):
    def extend(self, iterable: Iterable[CHUNK], /) -> None: ...
    def append(self, item: CHUNK, /) -> None: ...
    def __iter__(self) -> Iterable[CHUNK]: ...

RESPONSE_ACC = TypeVar("RESPONSE_ACC", bound="SupportsExtend[Any]")

P = ParamSpec("P")
T = TypeVar("T")

def stream(
    # accumulator: SupportsExtend[CHUNK] | Callable[[], SupportsExtend[CHUNK]]
) -> Callable[[Callable[P, AsyncGenerator[CHUNK, None]]], Callable[P, StreamController]]:
    def decorator(
        func: Callable[P, AsyncGenerator[Any, Any]]
    ) -> Callable[P, StreamController]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> StreamController:            
            return StreamController(gen_func=lambda: func(*args, **kwargs))
        return wrapper
    return decorator





def component(
    # accumulator: SupportsExtend[CHUNK] | Callable[[], SupportsExtend[CHUNK]]
) -> Callable[[Callable[P, AsyncGenerator[CHUNK | StreamController, None]]], Callable[P, PipeController]]:
    def decorator(func: Callable[P, AsyncGenerator[CHUNK | StreamController, None]]) -> Callable[P, PipeController]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> PipeController:
            return PipeController(gen_func=func, args=args, kwargs=kwargs)
        return wrapper
    return decorator