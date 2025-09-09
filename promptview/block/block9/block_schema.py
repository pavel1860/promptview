from queue import SimpleQueue
from .block import Block, BlockChunk, BlockSchema, AttrBlock, BlockSent
from .base_blocks import BaseBlock
from typing import Type




class BlockBuilderContext:
    
    
    def __init__(self, schema: Block):
        self.schema = self.extract_schema(schema)
        self.instance = None
        self.queue = SimpleQueue()
        
    # @property
    # def instance(self) -> Block:
    #     if self._instance is None:
    #         raise ValueError("Instance is not initialized")
    #     return self._instance
        
        
    def extract_schema(self, schema: Block) -> BlockSchema:
        def _clone_target_node(n: BlockSchema) -> BlockSchema:            
            r = n.copy({"children":[], "parent":None})                    
            return r
        
        def _is_target(node: BaseBlock) -> bool:
            return isinstance(node, BlockSchema)
        res = schema.gather_trees(_is_target, _clone_target_node)
        if len(res) == 1:
            return res[0]
        else:
            raise ValueError("Multiple target nodes found")  
        
    # def inst_root(self, content: BlockChunk | str | None = None) -> Block:
    #     self.instance = Block(
    #         self.schema.root,
    #         parent=None,
    #     )
    #     if content is not None:
    #         self.instance.append(content)
    #     return self.instance
    
    def has_events(self) -> bool:
        return not self.queue.empty()
    
    def get_event(self) -> Block:
        if self.queue.empty():
            raise ValueError("No events to get")
        return self.queue.get()
    
    def _push_event(self, event: Block):
        self.queue.put(event.model_dump())
        
        
    def get_view_info(self, view_name: str) -> tuple[BlockSchema, Block | None]:
        schema = self.schema.get(view_name)
        if schema is None:
            raise ValueError(f"View {view_name} not found")
        if not isinstance(schema, BlockSchema):
            raise ValueError(f"View {view_name} is not a schema")
        view = None
        if self.instance is not None:
            view = self.instance.get(view_name)
        return schema, view
    
    def get_block_path(self, target_schema: BlockSchema | str) -> list[BlockSchema]:        
        if isinstance(target_schema, str):
            view_schema = self.schema.get(target_schema)
            if view_schema is None:
                raise ValueError(f"View {view_schema} not found")
            if not isinstance(view_schema, BlockSchema):
                raise ValueError(f"View {view_schema} is not a schema")
        else:
            view_schema = target_schema
        if view_schema is None:
            raise ValueError(f"View {view_schema} not found")
        path_views = [view_schema]
        while (parent := path_views[0].parent) is not None:
            path_views.insert(0, parent)
        return path_views
    
    def inst_view(
        self, 
        view_schema: BlockSchema, 
        content: list[BlockChunk] | BlockChunk | str | None = None, 
        tags: list[str] | None = None, 
        attrs: dict[str, str] | None = None
    ) -> Block:
        
        def build_response_block(schema: BlockSchema) -> Block:
            if view_schema.name == schema.name:
                view = Block(
                    root=content,
                    tags=[t for t in schema.tags ] + (tags or []),
                )
                if attrs:
                    for k, v in attrs.items():
                        if k in schema.attrs:
                            value = schema.attrs[k].parse(v)
                            view.attrs[k] = value
                        else:
                            raise ValueError(f"Attribute {k} not found in schema")
                    
            else:
                view = Block(
                    root=schema.root.copy(),
                    tags=[t for t in schema.tags],
                )
            return view
        
        def insert(path: list[int], view: Block):
            if not path:
                self.instance = view
                return view
            else:
                if self.instance is None:
                    raise ValueError("Instance is not initialized")
                return self.instance.insert(view, path)

        curr_view = self.instance

        view_path = self.get_block_path(view_schema)
        for i, vw_scm in enumerate(view_path):
            pth_view = curr_view.get(vw_scm.name) if curr_view is not None else None
            if pth_view is None:
                pth_view = build_response_block(vw_scm)                
                insert(vw_scm.path, pth_view)
            curr_view = pth_view
            # if i == len(view_path) - 1:
            #     if content is not None:
            #         if isinstance(content, list):
            #             curr_view.root.extend(content)
            #         else:
            #             curr_view.root.append(content)
            #     if tags:
            #         curr_view.tags += tags
            #     if attrs:
            #         self.set_attributes(vw_scm.name, curr_view, attrs)
            self._push_event(curr_view)
        return curr_view
    
    
    def set_attributes(self, view_name: str, view: Block, attrs: dict[str, str]):
        schema = self.schema.get(view_name)
        if not schema:
            raise ValueError(f"Field {view_name} not found")
        if not isinstance(schema, BlockSchema):
            raise ValueError(f"Field {view_name} is not a schema")
        for k, v in attrs.items():
            if k in schema.attrs:
                value = schema.attrs[k].parse(v)
                view.attrs[k] = value
            else:
                raise ValueError(f"Attribute {k} not found in schema")
        return view
    
    
    # def append(
    #     self, 
    #     view_name: str, 
    #     content: list[BlockChunk] | BlockChunk | str | None = None,
    #     tags: list[str] | None = None,
    #     attrs: dict[str, str] | None = None,
    # ) -> Block:
    #     schema, view = self.get_view_info(view_name)
    #     if view is not None:
    #         if view.is_last_eol():
    #             blk = view.append(content)
    #         else:
    #             blk = view.inline_append(content)
            
    #         if attrs:
    #             self.set_attributes(view_name, blk, attrs)
    #         self._push_event(blk)
    #         return blk                
    #     else:             
    #         return self.inst_view(schema, content, tags, attrs)
    
    def append(
        self, 
        view_name: str, 
        content: list[BlockChunk] | BlockChunk | str | None = None,
        tags: list[str] | None = None,
        attrs: dict[str, str] | None = None,
    ) -> Block:
        schema, view = self.get_view_info(view_name)
        if view is not None:
            if view.is_last_eol():
                blk = view.append(content)
            else:
                blk = view.inline_append(content)
            
            if attrs:
                self.set_attributes(view_name, blk, attrs)
            self._push_event(blk)
            return blk  
        else:
            raise ValueError(f"View {view_name} is not instantiated")              
    
    def instantiate(self, view_name: str, content: list[BlockChunk] | BlockChunk | str | None = None, tags: list[str] | None = None, attrs: dict[str, str] | None = None) -> Block:
        schema, view = self.get_view_info(view_name)
        if view is not None:
            raise ValueError(f"View {view_name} is already instantiated")
        return self.inst_view(schema, content, tags, attrs)
    
    def print_schema_tree(self, verbose: bool = False):
        if self.schema is None:
            raise ValueError("Schema is not initialized")
        return self.schema.print_tree(verbose=verbose)
    
    def print_tree(self, verbose: bool = False):
        if self.instance is None:
            return "None"
        return self.instance.print_tree(verbose=verbose)
            
    
    
    def set_view_attr(
        self,
        view_name: str,
        postfix: BlockSent | None = None,
    ):
        schema, view = self.get_view_info(view_name)
        if postfix is not None:            
            if view is None:
                raise ValueError(f"View {view_name} not found")
            view.postfix = postfix
        
        return view
    
    
    
    def commit_view(
        self,
        view_name: str,
    ):
        schema, view = self.get_view_info(view_name)
        if view is None:
            raise ValueError(f"View {view_name} not found")
        # view.commit()
        return view