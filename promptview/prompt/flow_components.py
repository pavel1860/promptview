import asyncio
import json
from queue import SimpleQueue

import xml
from promptview.block.block7 import Block, BlockList
from promptview.prompt.parser import SaxStreamParser, StreamEvent




class BaseFbpComponent:
    
    def __init__(self, gen=None):
        self._gen = gen
    
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
    
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        raise NotImplementedError("BaseFbpComponent is not iterable")


class Stream(BaseFbpComponent):
    _index = 0

    def __aiter__(self):
        return self
        
    async def __anext__(self):
        try:
            self._index += 1
            return await self._gen.__anext__()
        except StopAsyncIteration:
            raise StopAsyncIteration

    async def asend(self, value):
        print(f"Intercepted asend({value})")
        # Optionally modify the value before sending
        return await self._gen.asend(value)

    async def athrow(self, typ, val=None, tb=None):
        return await self._gen.athrow(typ, val, tb)

    async def aclose(self):
        return await self._gen.aclose()
    

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
    
    async def __anext__(self):
        try:
            res = await self._gen.__anext__()
            # print(res)
            self._accumulator.append(res)
            return res
        except StopAsyncIteration:
            raise StopAsyncIteration


class StreamController:
    
    def __init__(self, gen_func, output_format=None):
        self._gen_func = gen_func
        self._flow = None
        self._stream = None
        self._output_format = output_format
        
    @property
    def acc(self):
        if self._acc is None:
            raise ValueError("StreamController is not initialized")
        return self._acc.result
    
    @property
    def index(self):
        if self._stream is None:
            raise ValueError("StreamController is not initialized")
        return self._stream._index
        
    async def __aiter__(self): 
        self._stream = Stream(self._gen_func())
        self._acc = Accumulator(BlockList())
        flow = self._stream | self._acc 
        if self._output_format:
            flow |= Parser()

        yield StreamEvent(type="stream_start")
        async for chunk in flow:
            if not isinstance(chunk, StreamEvent):
                yield StreamEvent(type="stream_delta", name=self._gen_func.__name__, payload=chunk)
            else:
                yield chunk
        yield StreamEvent(type="stream_end")
          
          
          
          
          
          
          
          
          
class PipeController:
    
    
    def __init__(self, gen_func):
        self._gen_func = gen_func
        self._stack = []
        
    @property
    def current(self):
        if not self._stack:
            raise ValueError("No current generator")
        return self._stack[-1]
    
    
    async def __aiter__(self):
        yield StreamEvent(type="span_start", name=self._gen_func.__name__)
        gen = self._gen_func()
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
                    async for res in pipe:
                        yield res
                    value = await gen.asend(pipe.current)
                    continue
                else:
                    value = await gen.asend(None)
                    yield StreamEvent(type="span_value", name=self._gen_func.__name__, payload=value)
        except StopAsyncIteration:
            yield StreamEvent(type="span_end", name=self._gen_func.__name__, payload=value)
            
            
            # yield StreamEvent(type="span_value", name=self._gen_func.__name__, payload=value)
        # yield StreamEvent(type="span_end", name=self._gen_func.__name__)j
    # async def __aiter__(self):
    #     yield StreamEvent(type="span_start", name=self._gen_func.__name__)
    #     gen = self._gen_func()
    #     async for value in gen:
    #         if isinstance(value, StreamController):
    #             async for chunk in value:
    #                 yield chunk
    #                 print(chunk)
    #             value.acc
    #             continue
    #         yield StreamEvent(type="span_value", name=self._gen_func.__name__, payload=value)
    #     yield StreamEvent(type="span_end", name=self._gen_func.__name__)