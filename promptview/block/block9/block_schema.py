from .block import Block, BlockSchema, FieldAttrBlock
from .base_blocks import BaseBlock
from typing import Type




class BlockBuilderContext:
    
    
    def __init__(self, schema: BlockSchema):
        self.schema = self.extract_schema(schema)
        self.instance = None
        
        
    def extract_schema(self, schema: BlockSchema) -> BlockSchema:
        def _clone_target_node(n: BlockSchema) -> BlockSchema:            
            r = n.copy(children=[], parent=None)                    
            return r
        
        def _is_target(node: BaseBlock) -> bool:
            return isinstance(node, BlockSchema)
        res = schema.gather_trees(_is_target, _clone_target_node)
        if len(res) == 1:
            return res[0]
        else:
            raise ValueError("Multiple target nodes found")      
