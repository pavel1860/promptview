import asyncio
import copy
from functools import wraps
import json
from queue import SimpleQueue
import datetime as dt

from typing import Any, AsyncGenerator, Callable, Iterable, Literal, ParamSpec, Protocol, Self, TypeVar, TYPE_CHECKING, runtime_checkable
import xml
from promptview.block.block7 import BlockChunk, BlockList, BlockSent, ResponseBlock
from promptview.prompt.injector import resolve_dependencies, resolve_dependencies_kwargs
from promptview.prompt.parser import BlockBuffer, SaxStreamParser
from promptview.prompt.events import StreamEvent
from promptview.utils.function_utils import call_function
from lxml import etree

from promptview.block import BlockSchema, Block
if TYPE_CHECKING:
    from promptview.model3.versioning.models import ExecutionSpan, SpanEvent, Log, span_type_enum
    



class BaseFbpComponent:
    
    def __init__(self, gen=None):
        self._gen = gen
        self._did_start = False
        self._did_yield = False
        self._did_end = False
        self._did_error = False
        self._last_value = None
        self._span = None
        
        
    @property
    def gen(self):
        if self._gen is None:
            raise ValueError(f"Flow generator ({self.__class__.__name__}) is not initialized")
        return self._gen
    
    @property
    def name(self):
        return self.gen.__name__
    

    
    

    
    def get_response(self):
        return self._last_value
    
    async def on_start_event(self, payload: Any = None, attrs: dict[str, Any] | None = None):
        raise NotImplementedError(f"Flow generator ({self.__class__.__name__}) does not implement on_start_event")
    
    async def on_value_event(self, payload: Any = None):
        raise NotImplementedError(f"Flow generator ({self.__class__.__name__}) does not implement on_value_event")
    
    async def on_stop_event(self, payload: Any = None):
        raise NotImplementedError(f"Flow generator ({self.__class__.__name__}) does not implement on_stop_event")
    
    async def on_error_event(self, error: Exception):
        raise NotImplementedError(f"Flow generator ({self.__class__.__name__}) does not implement on_error_event")
    
    async def on_start(self, value: Any = None):
        pass
    
    async def on_stop(self):
        pass
    
    async def on_error(self, error: Exception):
        pass
    
    
    async def pre_next(self):
        """
        This method is called before the next value is yielded.        
        """
        pass
    
    async def post_next(self, value: Any = None):
        """
        This method is called after the next value is yielded.
        """
        pass
    
    def __call__(self, _=None): return self
    
    def __or__(self, other: "BaseFbpComponent"):
        return self.pipe(other)
        # if isinstance(other, type):
        #     # `Parser | Accumulator` returns a callable
        #     return lambda x: other(self(x))
        # else:
        #     return other.__class__(self(other._gen))
    def __ior__(self, other: "BaseFbpComponent"):
        return self.pipe(other)
        
    def pipe(self, other: 'BaseFbpComponent'):
        other._gen = self
        return other
    
    
    async def start_generator(self):
        if self._did_start:
            raise RuntimeError(f"Generator ({self.__class__.__name__}) already started")
        await self.on_start()
        self._did_start = True
    
    def __aiter__(self):
        return self
    
    
    async def __anext__(self):
        try:
            if not self._did_start:
                await self.start_generator()
            value = await self.gen.__anext__()
            self._last_value = value
            if not self._did_yield:
                self._did_yield = True
            await self.post_next(value)
            return value
        except StopAsyncIteration:
            await self.on_stop()
            raise StopAsyncIteration
        except Exception as e:
            await self.on_error(e)
            raise e
    
    async def asend(self, value: Any = None):
        # print(f"Intercepted asend({value})")
        # Optionally modify the value before sending
        if not self._did_start:
            await self.on_start(value)
            self._did_start = True
        value = await self.gen.asend(value)
        self._last_value = value
        await self.post_next(value)
        return value

    async def athrow(self, typ, val=None, tb=None):
        return await self.gen.athrow(typ, val, tb)

    async def aclose(self):
        return await self.gen.aclose()



class Stream(BaseFbpComponent):
    _index = 0
    
    
    def __init__(self, gen: AsyncGenerator, name: str = "stream"):
        super().__init__(gen)
        self._name = name
        self._save_stream_dir: str | None = None
    

    def __aiter__(self):
        return self
    
    def save_stream(self, filepath: str):
        self._save_stream_dir = filepath        
    
    
    async def pre_next(self):
        self._index += 1
        
    async def post_next(self, value: Any = None):
        if self._save_stream_dir:
            with open(self._save_stream_dir, "a") as f:
                f.write(json.dumps(value.model_dump()) + "\n")
        return value
        
    async def on_stop(self):
        self._index -= 1
        
    # async def __anext__(self):
    #     try:
    #         self._index += 1
    #         return await self.gen.__anext__()
    #     except StopAsyncIteration:
    #         self._index -= 1
    #         raise StopAsyncIteration


            
    

class Parser(BaseFbpComponent):
      
    def __init__(self, response_schema: "Block", gen=None) -> None:
        super().__init__(gen)
        self.start_tag = "tag_start"
        self.end_tag = "tag_end"
        self.text_tag = "chunk"                
        self.response_schema = response_schema
        self._safety_tag = "stream_start"        
        self.response = response_schema.build_response()        
        self.parser2 = etree.XMLPullParser(events=("start", "end"))
        self.queue = SimpleQueue()
        self.block_list = []
        self._stream_started = False
        self._detected_tag = False
        
        self._tag_stack = []
        

    def __aiter__(self):
        return self
    
    def _push_tag(self, tag: str):
        self._tag_stack.append(tag)
    
    def _pop_tag(self):
        return self._tag_stack.pop()
    
    @property
    def current_tag(self):
        if not self._tag_stack:
            return None
        return self._tag_stack[-1]
    
        
    async def asend(self, value: Any = None):
        for i in range(20):            
            if not self._stream_started:
                self.parser2.feed(f'<{self._safety_tag}>')
                self._stream_started = True                
            if not self.queue.empty():
                return self.queue.get()
            value = await self.gen.asend(value) 
            print(value)
            self.block_list.append(value)
            self.parser2.feed(value.content)
            
            if "<" in value.content:
                self._detected_tag = True
            
            # in the middle of the stream, adding chunks to the current field
            if self.current_tag and not self._detected_tag:
                if field := self.response.get(self.current_tag):
                    value, sent = field.append_child_stream(value)
                    if sent is not None:
                        self.queue.put(copy.deepcopy(sent))
                    else:
                        self.queue.put(copy.deepcopy(value))
                else:
                    raise ValueError(f"Field '{self.current_tag}' not found in response schema")
            
            # start or end of a field, adding the whole field to the queue
            for event, element in self.parser2.read_events():
                if element.tag == self._safety_tag:
                    continue                
                if event == 'start':
                    # start of a field
                    self._push_tag(element.tag)
                    if field := self.response.get(element.tag):
                        for block in self.block_list:
                            field.append_root(block)
                        field.set_attributes(dict(element.attrib))
                        field.tags += [self.start_tag]
                        self.queue.put(copy.deepcopy(field))
                    else:
                        raise ValueError(f"Field '{element.tag}' not found in response schema")
                    self.block_list=[]
                    self._detected_tag = False                    
                elif event == 'end':
                    # end of a field
                    self._pop_tag()
                    is_end_event = False
                    end_sent = BlockSent(tags=[self.end_tag], sep="")
                    for block in self.block_list:
                        if "</" in block.content:
                            is_end_event = True                        
                        if is_end_event:
                            end_sent.append(block)
                    else:                        
                        if field := self.response.get(element.tag):                            
                            field.set_postfix(end_sent)
                            field.commit()
                            self.queue.put(copy.deepcopy(end_sent))
                    self.block_list=[]
                    self._detected_tag = False
                
                    
            if not self.queue.empty():
                return self.queue.get()
        else:
            raise StopAsyncIteration
        

    

class Accumulator(BaseFbpComponent):
    def __init__(self, accumulator) -> None:
        super().__init__(None)
        self._accumulator = accumulator
        
    @property
    def result(self):
        return self._accumulator
        
    def __aiter__(self):
        return self
    
    
    async def post_next(self, value: Any = None):
        return self._accumulator.append(value)
    
    # async def __anext__(self):
    #     try:
    #         res = await self._gen.__anext__()
    #         # print(res)
    #         self._accumulator.append(res)
    #         return res
    #     except StopAsyncIteration:
    #         raise StopAsyncIteration
  
@runtime_checkable
class Spanable(Protocol):
    index: int
    async def span_start(self, index: int, parent_span: "ExecutionSpan | None" = None):
        pass
    async def span_end(self):
        pass
    async def span_error(self, error: Exception):
        pass
    

    
    
CHUNK = TypeVar("CHUNK")

class SupportsExtend(Protocol[CHUNK]):
    def extend(self, iterable: Iterable[CHUNK], /) -> None: ...
    def append(self, item: CHUNK, /) -> None: ...
    def __iter__(self) -> Iterable[CHUNK]: ...

RESPONSE_ACC = TypeVar("RESPONSE_ACC", bound="SupportsExtend[Any]")

P = ParamSpec("P")
T = TypeVar("T")


class StreamController(BaseFbpComponent):
    
    def __init__(
        self, 
        gen: AsyncGenerator, 
        name:str,
        span_type: "span_type_enum" = "stream",
        response_schema=None, 
        acc_factory=None
    ):
        super().__init__(None)
        self._name = name
        self._stream = Stream(gen)
        self._gen = self._stream
        # self._acc = Accumulator(BlockList())
        # self._gen |= self._acc
        self._response_schema = response_schema
        # self._acc_factory = acc_factory or (lambda: BlockList(style="stream"))
        self._parser = None
        self.index = 0
        self._span_type = span_type
        self.parent: "PipeController | None" = None
        self._span: "ExecutionSpan | None" = None
        self.event: "SpanEvent | None" = None
        
        
    async def build_span(self, parent_span_id: str | None = None):
        from promptview.model3.versioning.models import ExecutionSpan
        self._span = await ExecutionSpan(
            span_type=self._span_type,
            name=self._name,
            index=self.index,
            start_time=dt.datetime.now(),
            parent_span_id=parent_span_id,
        ).save()
        return self._span
    
    @property
    def acc(self):
        if self._acc is None:
            raise ValueError("StreamController is not initialized")
        return self._acc.result
    
    @property
    def span(self):
        if self._span is None:
            raise ValueError(f"Span is not started for {self.__class__.__name__}")
        return self._span
    
    @property
    def span_id(self):
        return self.span.id

    def get_execution_path(self) -> list[int]:
        """Build execution path using existing index tracking"""
        path = []
        current = self
        while current:
            path.insert(0, current.index)  # Prepend to build path from root
            current = current.parent
        return path
    
    def get_response(self):
        if self._parser:
            return self._parser.response
        # return self.acc
        
    def parse(self, block_schema: "BlockSchema") -> Self:
        if self._parser is not None:
            raise ValueError("Parser already initialized")
        if self._gen is None:
            raise ValueError("StreamController is not initialized")
        self._parser = Parser(response_schema=block_schema)
        self._gen |= self._parser        
        return self
    
    def save(self, name: str, dir: str | None = None):
        import os
        path = f"{dir}/{name}.jsonl" if dir else f"{name}.jsonl"
        self._stream.save_stream(path)
        if os.path.exists(path):
            os.remove(path)
        return self
    
    def load(self, name: str, dir: str | None = None, delay: float = 0.07):
        import asyncio
        path = f"{dir}/{name}.jsonl" if dir else f"{name}.jsonl"
        
        async def load_stream():
            with open(path, "r") as f:
                for line in f:
                    await asyncio.sleep(delay)
                    j = json.loads(line)
                    block = BlockChunk.model_validate(j)
                    yield block
                    
        self._gen = Stream(load_stream())
        return self
    
                
    
    @property
    def name(self):
        return self._name


    # async def on_start(self, value: Any = None):
    #     from promptview.model3.versioning.models import ExecutionSpan
    #     self._span = await ExecutionSpan(
    #         span_type=self._span_type,
    #         name=self._name,
    #         index=self.index,
    #         start_time=dt.datetime.now(),
    #         parent_span_id=self.parent.span_id if self.parent else None,
    #     ).save()
    #     if self.parent:
    #         await self.parent.span.add_span(self.span, self.parent.index)
            
    async def on_stop(self):
        self.span.end_time = dt.datetime.now()
        self.span.status = "completed"
        self._span = await self.span.save()
        
    async def on_error(self, error: Exception):
        from promptview.model3.versioning.models import Log
        log = await Log(
            message=str(error),
            level="error"
        ).save()
        self.span.end_time = dt.datetime.now()
        self.span.status = "failed"
        self.span.metadata = {"error": str(error)}
        self._span = await self.span.save()
        self.stream_event = None
        
        
    
        
        
    
    
    async def on_start_event(self, payload: Any = None, attrs: dict[str, Any] | None = None):
        event = await self.span.add_stream(self.index)
        self.stream_event = event
        return StreamEvent(type="stream_start", name=self._name, payload=self.span, span_id=str(self.span_id), path=self.get_execution_path(), event=event)
    
    async def on_value_event(self, payload: Any = None):
        return StreamEvent(type="stream_delta", name=self._name, payload=payload, span_id=str(self.span_id), path=self.get_execution_path(), event=self.stream_event)
    
    async def on_stop_event(self, payload: Any = None):
        return StreamEvent(type="stream_end", name=self._name, span_id=str(self.span_id), path=self.get_execution_path(), event=self.stream_event)
    
    async def on_error_event(self, error: Exception):
        from promptview.model3.versioning.models import Log
        log = await Log(
            message=str(error),
            level="error"
        ).save()
        event = await self.span.add_log(log, self.index)
        return StreamEvent(type="stream_error", name=self._name, payload=error, span_id=str(self.span_id), path=self.get_execution_path(), event=event)
        
    async def __aiter__(self):
        return FlowRunner(self)
    
    async def stream_events(self):
        return FlowRunner(self).stream_events()
    


    async def stream(self, *args, **kwargs):
        raise NotImplementedError("StreamController is not streamable")
        yield
        
    @classmethod
    def decorator_factory(cls) -> Callable[[], Callable[[Callable[P, AsyncGenerator[CHUNK, None]]], Callable[P, Self]]]:
        def decorator_wrapper(
            # accumulator: SupportsExtend[CHUNK] | Callable[[], SupportsExtend[CHUNK]]
        ) -> Callable[[Callable[P, AsyncGenerator[CHUNK, None]]], Callable[P, Self]]:
            def decorator(
                func: Callable[P, AsyncGenerator[Any, Any]]
            ) -> Callable[P, Self]:
                @wraps(func)
                def wrapper(*args: P.args, **kwargs: P.kwargs) -> Self:            
                    return cls(gen=func(*args, **kwargs), name=func.__name__)
                return wrapper
            return decorator
        return decorator_wrapper



# def streamable(func: Callable[P, AsyncGenerator[CHUNK, None]]) -> Callable[P, StreamController]:
#     @wraps(func)
#     def wrapper(*args: P.args, **kwargs: P.kwargs) -> StreamController:
#         return StreamController(gen_func=func, args=args, kwargs=kwargs)
#     return wrapper



class PipeController(BaseFbpComponent):
    
    
    def __init__(
        self, 
        gen_func, 
        name: str, 
        span_type: "span_type_enum",
        args = (),
        kwargs = {}
    ):
        super().__init__(None)
        self._gen_func = gen_func
        self._args = args
        self._kwargs = kwargs
        self._name = name
        self._span_type = span_type
        self.parent: "PipeController | None" = None
        self._span: "ExecutionSpan | None" = None
        self.index = 0
        self.event: "SpanEvent | None" = None
    
    @property
    def span(self):
        if self._span is None:
            raise ValueError(f"Span is not started for {self.__class__.__name__}")
        return self._span

    @property
    def span_id(self):
        return self.span.id

    def get_execution_path(self) -> list[int]:
        """Build execution path using existing index tracking"""
        path = []
        current = self
        while current:
            path.insert(0, current.index)  # Prepend to build path from root
            current = current.parent
        return path
        
    async def on_start_event(self, payload: Any = None, attrs: dict[str, Any] | None = None):
        return StreamEvent(type="span_start", name=self._gen_func.__name__, payload=self.span, attrs=attrs, span_id=str(self.span_id), path=self.get_execution_path(), event=self.event)
    
    async def on_value_event(self, payload: Any = None):
        if isinstance(payload, StreamController):
            span = await payload.build_span(str(self.span_id))
            event = await self.span.add_span(span, self.index)
            payload.event = event
            return StreamEvent(type="span_value", name=self._gen_func.__name__, payload=span, span_id=str(self.span_id), path=self.get_execution_path(), event=event)
            
        elif isinstance(payload, PipeController):
            span = await payload.build_span(str(self.span_id))
            event = await self.span.add_span(span, self.index)
            payload.event = event
            return StreamEvent(type="span_value", name=self._gen_func.__name__, payload=span, span_id=str(self.span_id), path=self.get_execution_path(), event=event)
        elif isinstance(payload, Block):
            event = await self.span.add_block(payload, self.index)
            return StreamEvent(type="span_value", name=self._gen_func.__name__, payload=payload, span_id=str(self.span_id), path=self.get_execution_path(), event=event)
        else:
            raise ValueError(f"Invalid payload type: {type(payload)}")
            return StreamEvent(type="span_value", name=self._gen_func.__name__, payload=payload, span_id=str(self.span_id), path=self.get_execution_path())
    
    async def on_stop_event(self, payload: Any = None):
        return StreamEvent(type="span_end", name=self._gen_func.__name__, payload=payload, span_id=str(self.span_id), path=self.get_execution_path(), event=self.event)
    
    async def on_error_event(self, error: Exception):
        from promptview.model3.versioning.models import Log
        log = await Log(
            message=str(error),
            level="error"
        ).save()
        event = await self.span.add_log(log, self.index)
        return StreamEvent(type="span_error", name=self._gen_func.__name__, payload=error, span_id=str(self.span_id), path=self.get_execution_path(), event=event)
    
    async def post_next(self, value: Any = None):
        self.index += 1
        return value
    
    # async def post_next(self, value: Any = None):
    #     from promptview.model3.versioning.models import Turn
    #     if isinstance(value, Block):
    #         turn = Turn.current()
    #         if turn:
    #             await turn.add_block(value, self.index, span_id=self.span_id)
    #             self.index += 1
    #     return value
    
    # async def post_next(self, value: Any = None):
    #     from promptview.model3.versioning.models import ExecutionSpan
    #     if isinstance(value, Block):
    #         await self.span.add_block(value, self.index)
    #         self.index += 1
    #     return value
    
    async def build_span(self, parent_span_id: str | None = None):
        from promptview.model3.versioning.models import ExecutionSpan
        self._span = await ExecutionSpan(
            span_type=self._span_type,
            name=self._name,
            index=self.index,
            start_time=dt.datetime.now(),
            parent_span_id=parent_span_id,
        ).save()
        return self._span
    
    async def add_span(self, span: "ExecutionSpan"):
        event = await self.span.add_span(span, self.index)
        return event
    
    
    async def add_event(self, gen: "PipeController | StreamController"):
        if isinstance(gen, StreamController):
            span = await gen.build_span(str(self.span_id))
            event = await self.span.add_span(span, self.index)
            gen.event = event
            return event
        elif isinstance(gen, PipeController):
            span = await gen.build_span(str(self.span_id))
            event = await self.span.add_span(span, self.index)        
            gen.event = event
            return event
        else:
            raise ValueError(f"Invalid generator type: {type(gen)}")

    async def on_start(self, value: Any = None):
        from promptview.model3.versioning.models import ExecutionSpan
        bound, kwargs = await resolve_dependencies_kwargs(self._gen_func, self._args, self._kwargs)
        self._gen = self._gen_func(*bound.args, **bound.kwargs)
        if not self._span:
            self._span = await ExecutionSpan(
                span_type=self._span_type,
                name=self._name,
                index=self.index,
                parent_span_id=self.parent.span_id if self.parent else None,
            ).save()
        
        
    async def on_stop(self):
        self.span.end_time = dt.datetime.now()
        self.span.status = "completed"
        self._span = await self.span.save()
        
    async def on_error(self, error: Exception):
        from promptview.model3.versioning.models import Log
        log = await Log(
            message=str(error),
            level="error"
        ).save()
        await self.span.add_log(log, self.index)
        self.span.end_time = dt.datetime.now()
        self.span.status = "failed"
        self.span.metadata = {"error": str(error)}
        self._span = await self.span.save()
    
    def __aiter__(self):
        return FlowRunner(self)
    
    def stream_events(self):
        return FlowRunner(self).stream_events()
            
    @classmethod
    def decorator_factory(cls) -> Callable[[], Callable[[Callable[P, AsyncGenerator[CHUNK, None]]], Callable[P, Self]]]:
        def component_decorator(
            # accumulator: SupportsExtend[CHUNK] | Callable[[], SupportsExtend[CHUNK]]
        ) -> Callable[[Callable[P, AsyncGenerator[CHUNK | StreamController, None]]], Callable[P, Self]]:
            def decorator(func: Callable[P, AsyncGenerator[CHUNK | StreamController, None]]) -> Callable[P, Self]:
                @wraps(func)
                def wrapper(*args: P.args, **kwargs: P.kwargs) -> Self:
                    return cls(gen_func=func, args=args, kwargs=kwargs)
                return wrapper
            return decorator
        return component_decorator



class FlowRunner:
    def __init__(self, gen: BaseFbpComponent):
        self.stack: list[BaseFbpComponent] = [gen]
        self.last_value: Any = None
        self._output_events = False
        self._error_to_raise = None
        self._last_gen = None
        
        
    @property
    def current(self):
        if not self.stack:
            raise StopAsyncIteration
            # raise ValueError("Stack is empty")
        return self.stack[-1]
    
    @property
    def should_output_events(self):
        if self._output_events:
            return True
        return False
    
    def push(self, value: BaseFbpComponent):
        self.stack.append(value)
        
    def pop(self):
        gen = self.stack.pop()
        self._last_gen = gen
        return gen
    
    
    def __aiter__(self):
        return self
    
    def _get_response(self):
        if self._last_gen:
            res = self._last_gen.get_response()
            self._last_gen = None
            return res
        else:
            last_yield = self.current._last_value
            if last_yield:
                return last_yield    
        return None
    
    
    def _try_to_gen_event(self, func: Callable[[], Any], value: Any):
        if isinstance(value, StreamEvent):
            return value
        return func(value)

    

    async def __anext__(self):
        
        # yield StreamEvent(type="span_start", name=gen.name, attrs=kwargs )
        if self._error_to_raise:
            raise self._error_to_raise
        
        value = None
        while self.stack:
            
            try:
                gen = self.current            
                if not gen._did_start:
                    await gen.start_generator()                    
                    payload = gen.span if isinstance(gen, PipeController) and len(self.stack) == 1 else None
                    event = await gen.on_start_event(payload)
                    if not self.should_output_events:
                        continue
                    return event
                    

                response = self._get_response()
                value = await gen.asend(response)
                
                if isinstance(value, StreamController):
                    self.push(value)
                elif isinstance(value, PipeController):
                    self.push(value)
                
                self.last_value = value
                event = await gen.on_value_event(value)
                if not self.should_output_events:
                    return value
                return event
                
                # if isinstance(value, StreamController):
                #     span = await value.build_span(str(gen.span_id))
                #     event = await gen.add_span(span)
                #     value.event = event
                #     self.push(value)
                #     if self.should_output_events:
                #         se = gen.on_value_event(event)
                #         se.event = event
                #         return se
                # elif isinstance(value, PipeController):
                #     span = await value.build_span(str(gen.span_id))
                #     event = await gen.add_span(span)
                #     value.event = event
                #     self.push(value)
                #     if self.should_output_events:
                #         se = gen.on_value_event(event)
                #         se.event = event
                #         return se                    
                # else:
                #     self.last_value = value
                #     if not self.should_output_events:
                #         return value                    
                #     # return self._try_to_gen_event(gen.on_value_event, value)
                #     return gen.on_value_event(value)
                                
                # if isinstance(value, StreamController):
                #     event = await gen.add_event(span)
                #     if self.should_output_events:
                #         return gen.on_value_event(event)
                #     self.push(value)
                # elif isinstance(value, PipeController):
                #     value.parent = self.current
                #     self.push(value)
                # else:
                #     self.last_value = value
                #     if not self.should_output_events:
                #         return value
                #     # return self._try_to_gen_event(gen.on_value_event, value)
                #     return gen.on_value_event(value)
            except StopAsyncIteration:
                gen = self.pop()
                await gen.on_stop()
                event = await gen.on_stop_event(None)
                if not self.should_output_events:
                    continue
                return event
            except Exception as e:
                gen = self.pop()
                event = await gen.on_error_event(e)
                await gen.on_error(e)                
                if not self.should_output_events:
                    raise e
                self._error_to_raise = e
                return event
        else:
            raise StopAsyncIteration

    
    def stream_events(self):
        self._output_events = True
        return self
    
    
    
    

