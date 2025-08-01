import asyncio
import json
from queue import SimpleQueue

from typing import Any
import xml
from promptview.block.block7 import Block, BlockList
from promptview.prompt.injector import resolve_dependencies, resolve_dependencies_kwargs
from promptview.prompt.parser import SaxStreamParser
from promptview.prompt.events import StreamEvent
from promptview.utils.function_utils import call_function




class BaseFbpComponent:
    
    def __init__(self, gen=None):
        self._gen = gen
        self._did_start = False
        self._did_yield = False
        self._did_end = False
        self._did_error = False
        
        
    @property
    def gen(self):
        if self._gen is None:
            raise ValueError(f"Flow generator ({self.__class__.__name__}) is not initialized")
        return self._gen
    
    @property
    def name(self):
        return self.gen.__name__
    
    def on_start_event(self, payload: Any = None, attrs: dict[str, Any] | None = None):
        raise NotImplementedError(f"Flow generator ({self.__class__.__name__}) does not implement on_start_event")
    
    def on_value_event(self, payload: Any = None):
        raise NotImplementedError(f"Flow generator ({self.__class__.__name__}) does not implement on_value_event")
    
    def on_stop_event(self, payload: Any = None):
        raise NotImplementedError(f"Flow generator ({self.__class__.__name__}) does not implement on_stop_event")
    
    def on_error_event(self, error: Exception):
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
        await self.post_next(value)
        return value

    async def athrow(self, typ, val=None, tb=None):
        return await self.gen.athrow(typ, val, tb)

    async def aclose(self):
        return await self.gen.aclose()



class Stream(BaseFbpComponent):
    _index = 0
    

    def __aiter__(self):
        return self
    
    
    async def pre_next(self):
        self._index += 1
        
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
    def __init__(self, gen=None) -> None:
        super().__init__(gen)
        self.start_tag = "tag_start"
        self.end_tag = "tag_end"
        self.text_tag = "chunk"                
        self.queue = SimpleQueue()        
        self.handler = SaxStreamParser(
            self.queue, 
            self.start_tag, 
            self.end_tag, 
            self.text_tag
        )
        self.parser = xml.sax.make_parser()
        self.parser.setFeature(xml.sax.handler.feature_external_ges, False)        
        self.parser.setContentHandler(self.handler)
        self.block_stack = []

    def __aiter__(self):
        return self
    
    def advance(self):
        event = self.queue.get() 
        # print("<<", event.type, event.payload)       
        if event.type == self.start_tag:
            return event
        elif event.type == self.end_tag:
            return event
        elif event.type == self.text_tag:
            if self.block_stack:
                block = self.block_stack.pop() 
                event.payload = block                                   
            return event
        else:
            raise ValueError(f"Unexpected event: {event}")
    
    
    def feed(self, value):
        if isinstance(value, Block):
            self.block_stack.append(value)
            value = value.content
        # print(">>", value)
        self.parser.feed(value)
    
    async def __anext__(self):
        for i in range(20):
            if not self.queue.empty():
                return self.advance()
            else:
                value = await self._gen.__anext__()
                self.feed(value)
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


class StreamController(BaseFbpComponent):
    
    def __init__(self, gen_func=None, output_format=None, acc_factory=None, args=(), kwargs={}):
        super().__init__(None)
        self._gen_func = gen_func or self.stream
        self._flow = None
        self._stream = None
        self._output_format = output_format
        self._acc_factory = acc_factory or BlockList
        self._kwargs = kwargs
        self._args = args

        
    @property
    def acc(self):
        if self._acc is None:
            raise ValueError("StreamController is not initialized")
        return self._acc.result
    
    @property
    def name(self):
        return self._gen_func.__name__
    
    # async def asend(self, value: Any = None):
    #     return await self._stream.__anext__()
    
    @property
    def index(self):
        if self._stream is None:
            raise ValueError("StreamController is not initialized")
        return self._stream._index
    
    async def on_start(self, value: Any = None):
        self._stream = Stream(self._gen_func(*self._args, **self._kwargs))
        self._acc = Accumulator(self._acc_factory())
        self._flow = self._stream | self._acc 
        if self._output_format:
            self._flow |= Parser()
        self._gen = self._flow
    
    
    def on_start_event(self, payload: Any = None, attrs: dict[str, Any] | None = None):
        return StreamEvent(type="stream_start", name=self._gen_func.__name__)
    
    def on_value_event(self, payload: Any = None):
        return StreamEvent(type="stream_delta", name=self._gen_func.__name__, payload=payload)
    
    def on_stop_event(self, payload: Any = None):
        return StreamEvent(type="stream_end", name=self._gen_func.__name__)
    
    def on_error_event(self, error: Exception):
        return StreamEvent(type="stream_error", name=self._gen_func.__name__, payload=error)
        
    def __aiter__(self):
        return FlowRunner(self)
    
    def stream_events(self):
        return FlowRunner(self).stream_events()
    
    async def __aiter__3(self): 
        self._stream = Stream(self._gen_func(*self._args, **self._kwargs))
        self._acc = Accumulator(self._acc_factory())
        flow = self._stream | self._acc 
        if self._output_format:
            flow |= Parser()

        yield StreamEvent(type="stream_start", name=self._gen_func.__name__)
        async for chunk in flow:
            if not isinstance(chunk, StreamEvent):
                yield StreamEvent(type="stream_delta", name=self._gen_func.__name__, payload=chunk)
            else:
                yield chunk
        yield StreamEvent(type="stream_end", name=self._gen_func.__name__)


    async def stream(self, *args, **kwargs):
        raise NotImplementedError("StreamController is not streamable")
        yield



class PipeController(BaseFbpComponent):
    
    
    def __init__(self, gen_func, args = (), kwargs = {}):
        super().__init__(None)
        self._gen_func = gen_func
        self._args = args
        self._kwargs = kwargs
        
        
    def on_start_event(self, payload: Any = None, attrs: dict[str, Any] | None = None):
        return StreamEvent(type="span_start", name=self._gen_func.__name__, attrs=attrs)
    
    def on_value_event(self, payload: Any = None):
        return StreamEvent(type="span_value", name=self._gen_func.__name__, payload=payload)
    
    def on_stop_event(self, payload: Any = None):
        return StreamEvent(type="span_end", name=self._gen_func.__name__, payload=payload)
    
    def on_error_event(self, error: Exception):
        return StreamEvent(type="span_error", name=self._gen_func.__name__, payload=error)
        

    async def on_start(self, value: Any = None):
        bound, kwargs = await resolve_dependencies_kwargs(self._gen_func, self._args, self._kwargs)
        self._gen = self._gen_func(*bound.args, **bound.kwargs)
    
    def __aiter__(self):
        return FlowRunner(self)
    
    def stream_events(self):
        return FlowRunner(self).stream_events()
    
    async def __aiter__2(self):
        # bound = await resolve_dependencies(self._gen_func, self._args, self._kwargs)
        # gen = self._gen_func(*bound.args, **bound.kwargs)
        bound, kwargs = await resolve_dependencies_kwargs(self._gen_func, self._args, self._kwargs)
        gen = self._gen_func(*bound.args, **bound.kwargs)
        yield StreamEvent(type="span_start", name=gen.__name__, attrs=kwargs )        
        value = await gen.asend(None)
        try:      
            while True:
                if isinstance(value, StreamController):
                    stream = value
                    async for chunk in stream:
                        yield chunk
                        # print(chunk)
                    value = await gen.asend(stream.acc)
                    # yield StreamEvent(type="span_value", name=self._gen_func.__name__, payload=value)
                    continue
                elif isinstance(value, PipeController):
                    pipe = value
                    res = None
                    async for res in pipe:
                        yield res
                    value = await gen.asend(res.payload if res else None)
                    continue
                else:
                    yield StreamEvent(type="span_value", name=self._gen_func.__name__, payload=value)
                    value = await gen.asend(value)                    
        except StopAsyncIteration:
            yield StreamEvent(type="span_end", name=self._gen_func.__name__, payload=value)
            




class FlowRunner:
    def __init__(self, gen: BaseFbpComponent):
        self.stack: list[BaseFbpComponent] = [gen]
        self.last_value: Any = None
        self._output_events = False
        self._error_to_raise = None
        
        
    @property
    def current(self):
        if not self.stack:
            raise StopAsyncIteration
            # raise ValueError("Stack is empty")
        return self.stack[-1]
    
    def push(self, value: BaseFbpComponent):
        self.stack.append(value)
        
    def pop(self):
        return self.stack.pop()
    
    
    def __aiter__(self):
        return self
    
    
    

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
                    if not self._output_events:
                        continue
                    return gen.on_start_event()
                # elif gen._did_end:
                #     self.pop()                
                #     return gen.on_stop_event()            
                value = await gen.asend(None)            
                                
                if isinstance(value, StreamController):
                    self.push(value)
                elif isinstance(value, PipeController):
                    self.push(value)
                else:
                    self.last_value = value
                    if not self._output_events:
                        return value
                    return gen.on_value_event(value)
            except StopAsyncIteration:
                gen = self.pop()
                if not self._output_events:
                    continue
                return gen.on_stop_event(None)
            except Exception as e:
                gen = self.pop()
                if not self._output_events:
                    raise e
                self._error_to_raise = e
                return gen.on_error_event(e)
        else:
            raise StopAsyncIteration

    
    def stream_events(self):
        self._output_events = True
        return self
