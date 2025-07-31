from dataclasses import dataclass
import xml.sax
from typing import AsyncGenerator
from queue import SimpleQueue

from promptview.block.block import Block




@dataclass
class StreamEvent:
    type: str
    name: str | None = None
    attrs: dict | None = None
    depth: int = 0
    payload: str | None = None


class SaxStreamParser(xml.sax.ContentHandler):
            
    start_tag: str = 'tag_start'
    end_tag: str = 'tag_end'
    text_tag: str = 'chunk'
    
    def __init__(self, queue: SimpleQueue, start_tag: str | None = None, end_tag: str | None = None, text_tag: str | None = None):
        self.start_tag = start_tag or self.start_tag
        self.end_tag = end_tag or self.end_tag
        self.text_tag = text_tag or self.text_tag
        self.queue = queue
        self.buffer = []
        self.depth = 0
        self.current_tag = None

    def startElement(self, name, attrs):
        text = self.flush_buffer()
        self.queue.put(StreamEvent(type=self.start_tag, name=name, attrs=dict(attrs), depth=self.depth, payload=text))
        self.current_tag = name
        self.buffer = []
        self.depth += 1

    def characters(self, content):
        self.buffer.append(content)
        self.queue.put(StreamEvent(type=self.text_tag, name = self.current_tag, payload=content, depth=self.depth))

    def endElement(self, name):
        text = self.flush_buffer()
        self.depth -= 1
        self.queue.put(StreamEvent(type=self.end_tag, name=name, payload=text, depth=self.depth))

    def flush_buffer(self):
        text = ''.join(self.buffer).strip()
        if text:
            return text
        self.buffer = []
        
        
        
        
        
        
        
async def stream_parser(
    stream: AsyncGenerator[str, None], 
    start_tag: str | None = None, 
    end_tag: str | None = None, 
    text_tag: str | None = None
    ) -> AsyncGenerator[StreamEvent, None]:
    queue = SimpleQueue()
    handler = SaxStreamParser(queue, start_tag, end_tag, text_tag)

    parser = xml.sax.make_parser()
    parser.setFeature(xml.sax.handler.feature_external_ges, False)
    parser.setContentHandler(handler)
    
    async for chunk in stream:
        parser.feed(chunk)
        while not queue.empty():
            yield queue.get()
    parser.close()





class StreamParser:
    def __init__(
        self,
        stream: AsyncGenerator[str, None],
        start_tag: str | None = None,
        end_tag: str | None = None,
        text_tag: str | None = None
    ):
        self.stream = stream
        self.queue = SimpleQueue()
        self.handler = SaxStreamParser(self.queue, start_tag, end_tag, text_tag)

        self.parser = xml.sax.make_parser()
        self.parser.setFeature(xml.sax.handler.feature_external_ges, False)
        self.parser.setContentHandler(self.handler)
        self._chunk_iter = self._generator()

    def __aiter__(self):
        self._chunk_iter = self._generator()
        return self
    

    async def __anext__(self):
        return await self._chunk_iter.__anext__()
    
    def preprocess(self, chunk: Block):
        return chunk.content
    
    def postprocess(self, event: StreamEvent):
        return 

    async def _generator(self):
        async for chunk in self.stream:
            self.parser.feed(chunk)
            while not self.queue.empty():
                yield self.queue.get()
        self.parser.close()