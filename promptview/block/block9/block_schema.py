from queue import SimpleQueue
from .block import Block, BlockChunk, BlockSchema, AttrBlock
from .base_blocks import BaseBlock
from typing import Type




class BlockBuilderContext:
    
    
    def __init__(self, schema: BlockSchema):
        self.schema = self.extract_schema(schema)
        self.instance = None
        self.queue = SimpleQueue()
        
    # @property
    # def instance(self) -> Block:
    #     if self._instance is None:
    #         raise ValueError("Instance is not initialized")
    #     return self._instance
        
        
    def extract_schema(self, schema: BlockSchema) -> BlockSchema:
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
    
    def get_block_path(self, target_schema: BlockSchema | str) -> list[BlockSchema]:        
        if isinstance(target_schema, str):
            field_schema = self.schema.get(target_schema)
            if field_schema is None:
                raise ValueError(f"Field {field_schema} not found")
            if not isinstance(field_schema, BlockSchema):
                raise ValueError(f"Field {field_schema} is not a schema")
        else:
            field_schema = target_schema
        if field_schema is None:
            raise ValueError(f"Field {field_schema} not found")
        path_fields = [field_schema]
        while (parent := path_fields[0].parent) is not None:
            path_fields.insert(0, parent)
        return path_fields
    
    def inst_view(self, view_schema: BlockSchema, content: BlockChunk | str | None = None) -> Block:
        
        def build_response_block(schema: BlockSchema) -> Block:
            res = Block(
                schema.root.copy(),
                tags=[t for t in schema.tags],
            )
            return res
        
        def insert(path: list[int], view: Block):
            if not path:
                self.instance = view
                return view
            else:
                if self.instance is None:
                    raise ValueError("Instance is not initialized")
                return self.instance.insert(view, path)

        curr_view = self.instance
        # for fld in self.get_block_path(field_schema):
        view_path = self.get_block_path(view_schema)
        for i, vw_scm in enumerate(view_path):
            pth_view = curr_view.get(vw_scm.name) if curr_view else None
            if pth_view is None:
                pth_view = build_response_block(vw_scm)                
            # curr.append(ex_flt)
            insert(vw_scm.path, pth_view)
            curr_view = pth_view
            if i == len(view_path) - 1 and content is not None:
                curr_view.append(content)
            self._push_event(curr_view)
        return curr_view
    
    
    def append(self, view_name: str, content: BlockChunk | str | None = None) -> Block:
        if self.instance is not None and (view:=self.instance.get(view_name)):
            if view.is_last_eol():
                blk = view.append(content)
                self._push_event(blk)
                return blk
            else:
                blk = view.inline_append(content)
                self._push_event(blk)
                return blk
        else: 
            field_schema = self.schema.get(view_name)
            if field_schema is None:
                raise ValueError(f"Field {view_name} not found")
            if not isinstance(field_schema, BlockSchema):
                raise ValueError(f"Field {view_name} is not a schema")
            return self.inst_view(field_schema, content)
    
    def print_schema_tree(self, verbose: bool = False):
        if self.schema is None:
            raise ValueError("Schema is not initialized")
        return self.schema.print_tree(verbose=verbose)
    
    def print_tree(self, verbose: bool = False):
        if self.instance is None:
            return "None"
        return self.instance.print_tree(verbose=verbose)
            
        