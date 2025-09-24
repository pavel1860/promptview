import asyncio
import asyncpg
import hashlib
import json
import uuid
from typing import Any, Dict, List, Literal, Optional
from promptview.block import BaseBlock, Block, BlockChunk, BlockList, BlockSent
from promptview.model.versioning import Branch
from promptview.model3.sql.expressions import RawValue
from promptview.model3.sql.queries import Column
from promptview.utils.db_connections import PGConnectionManager
import datetime as dt
# from promptview.model3.block_models.block_models import BlockNode, BlockModel
from promptview.model3.versioning.models import BlockTree, BlockNode, BlockModel, ExecutionSpan, TurnStatus



def block_hash(content: Optional[str] = None, json_content: Optional[dict] = None) -> str:
    if content is not None:
        data = content.encode("utf-8")
    else:
        data = json.dumps(json_content, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()

def flatten_tree(data: Dict[str, Any], base_path: str = "1") -> List[Dict[str, Any]]:
    flat = [{
        "path": base_path,
        "content": data.get("content"),
        "json_content": data.get("json_content"),
        "style": data.get("style", {}),
    }]
    for idx, child in enumerate(data.get("children", []), start=1):
        flat.extend(flatten_tree(child, f"{base_path}.{idx}"))
    return flat


def dump_chunk(chunk: BlockChunk):
    # dump = {
    #     "content": chunk.content,
    # }
    # if chunk.logprob is not None:
    #     dump["logprob"] = chunk.logprob
    # if chunk.prefix is not None:
    #     dump["prefix"] = chunk.prefix
    # if chunk.postfix is not None:
    #     dump["postfix"] = chunk.postfix
    return {
        "content": chunk.content,
        "logprob": chunk.logprob,
        "prefix": chunk.prefix,
        "postfix": chunk.postfix,
    }

def dump_sent(sent: BlockSent):   
    chunks = []    
    for chunk in sent.children:        
        chunks.append(dump_chunk(chunk))
    return {
        # "has_eol": sent.has_eol,
        "content": sent.content,
        "children": chunks,
    }
    
def load_sent_dump(dump: dict):
    sent = BlockSent(
        content=dump["content"],
    )
    for child in dump["children"]:
        sent.append(
            BlockChunk(
                content=child["content"],
                logprob=child["logprob"],
            )       
        )
    return sent

def dump_block(blk: Block):
    dumps = []
    for blk in blk.traverse():
        dump = {}
        dump["content"] = blk.content.render()
        dump["json_content"] = {
            "content": dump_sent(blk.content),
            "prefix": dump_sent(blk.prefix) if blk.prefix is not None else None,
            "postfix": dump_sent(blk.postfix) if blk.postfix is not None else None,
        }
        dump["styles"] = blk.styles
        dump["path"] = ".".join(str(p) for p in [0] +blk.path)
        dump["tags"] = blk.tags
        dump["role"] = blk.role
        dump["attrs"] = blk.attrs
        dumps.append(dump)
    return dumps


def load_block_dump(dumps: list[dict]):
    block_lookup = {}
    for dump in dumps:
        blk = Block(
            load_sent_dump(dump['block']["json_content"]['content']),
            role=dump["role"],
            styles=dump["styles"], 
            attrs=dump["attrs"],
            tags=dump["tags"],
            prefix=load_sent_dump(dump['block']["json_content"]['prefix']) if dump['block']["json_content"]['prefix'] is not None else None,
            postfix=load_sent_dump(dump['block']["json_content"]['postfix']) if dump['block']["json_content"]['postfix'] is not None else None,
        )
        block_lookup[dump["path"]] = blk
    
    root_blk = block_lookup.pop("0")
    for p, blk in block_lookup.items():
        path = [int(p_i) for p_i in p.split(".")]
        root_blk.insert(blk, path[1:])
        
    return root_blk


  
    
    

async def insert_block(block: Block, branch_id: int, turn_id: int, span_id: uuid.UUID | None = None) -> str:
    """
    Alternative implementation using executemany for bulk inserts.
    This approach is cleaner and more straightforward than UNNEST.
    """
    nodes = dump_block(block)
    async with PGConnectionManager.transaction() as tx:
        tree_id = str(uuid.uuid4())
        created_at = dt.datetime.now()
        await tx.execute(
            "INSERT INTO block_trees (id, created_at, branch_id, turn_id, span_id) VALUES ($1, $2, $3, $4, $5)", 
            tree_id, created_at, branch_id, turn_id, span_id
        )

        # --- prepare rows for blocks ---
        block_rows = []
        for node in nodes:
            blk_id = block_hash(node["content"], node["json_content"])
            block_rows.append((blk_id, node["content"], json.dumps(node["json_content"])))

        # --- bulk insert blocks using executemany ---
        if block_rows:
            await tx.executemany(
                "INSERT INTO blocks (id, content, json_content) VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
                block_rows
            )

        # --- prepare rows for nodes ---
        node_rows = []
        for node in nodes:
            blk_id = block_hash(node["content"], node["json_content"])
            # Convert lists to arrays for PostgreSQL
            styles_array = node["styles"] if node["styles"] is not None else []
            tags_array = node["tags"] if node["tags"] is not None else []            
            node_rows.append((
                tree_id, 
                node["path"], 
                blk_id, 
                styles_array, 
                node["role"], 
                tags_array, 
                json.dumps(node["attrs"])
            ))

        # --- bulk insert nodes using executemany ---
        if node_rows:
            await tx.executemany(
                "INSERT INTO block_nodes (tree_id, path, block_id, styles, role, tags, attrs) VALUES ($1, $2::ltree, $3, $4, $5, $6, $7)",
                node_rows
            )

        return tree_id
    

    
    
    
    
async def get_blocks(tree_ids: list[str], dump_models: bool = True) -> dict[str, Block]:
    block_trees = await BlockTree.query(alias="bt").select("*").include(
            BlockNode.query(alias="bn").select("*").include(
                BlockModel.query(alias="bm").select("*")
            )
        ).where(lambda b: b.id.isin(tree_ids)).json()
    blocks = {}
    for tree in block_trees:
        tree_id = str(tree["id"])
        block = load_block_dump(tree["nodes"])
        blocks[tree_id] = block.model_dump() if dump_models else block
    return blocks







class BlockLogQuery:
    
    def __init__(
        self,
        limit: int | None = None,
        offset: int | None = None,
        direction: Literal["asc", "desc"] = "desc",
        span_name: str | None = None,
        statuses: list[TurnStatus] = [TurnStatus.COMMITTED, TurnStatus.STAGED],
    ):
        self.limit = limit or 5
        self.offset = offset
        self.direction = direction
        self.span_name = span_name
        self.statuses = statuses
        # self.query = self._build_block_query() if not span_name else self._build_span_query()
        
    def __await__(self):
        return self.execute().__await__()
    
    async def execute(self) -> List[Block]:
        query = self._build_block_query() if not self.span_name else self._build_span_query()
        def tree_to_block(tree):
            # print(tree)
            if not tree['nodes']:
                return None
            return load_block_dump(tree['nodes'])
        query = query.parse(tree_to_block)
        return await query.json()
        
    def _build_block_query(self):
        # if self.span_name:
        #     return ExecutionSpan.vquery(
        #         limit=self.limit, 
        #         offset=self.offset, 
        #         direction=self.direction
        #     ).select("*").include(BlockTree.query(alias="bt").include(BlockNode.query(alias="bn").include(BlockModel))).where(name=self.span_name)
        return BlockTree.vquery(
            alias="bt", 
            limit=self.limit, 
            offset=self.offset, 
            direction=self.direction,
            statuses=self.statuses
        ).include(
            BlockNode.query(alias="bn").order_by("id").include(BlockModel)
        ).order_by("created_at")
        
    def _build_span_query(self):
        return ExecutionSpan.vquery(
            alias="es", 
            limit=self.limit, 
            offset=self.offset, 
            direction=self.direction,
            statuses=self.statuses            
        ).include(BlockTree.query(alias="bt").include(BlockNode.query(alias="bn").include(BlockModel))).where(name=self.span_name)
        
    def where(self, span: str | None = None):
        if span:
            self.span_name = span
        return self
    
    
    def last(self, limit: int):
        self.limit = limit
        return self
    
    def all(self):
        self.statuses = []
        return self
    
    def span(self, span: str):
        self.span_name = span
        self.query = self._build_span_query()
        return self
    
    def print(self):
        return self.query.print()
        

class BlockLog:
    
    def __init__(self):
        self.query = None
        
        
    @classmethod
    def last(cls, limit: int) -> BlockLogQuery:
        return BlockLogQuery(limit=limit)

    @classmethod
    def span(cls, span: str) -> BlockLogQuery:
        return BlockLogQuery(span_name=span)
    
    

    
    @classmethod
    async def add(cls, block: Block, branch_id: int | None = None, turn_id: int | None = None, span_id: uuid.UUID | None = None):
        from promptview.model3.versioning.models import Turn, Branch
        if branch_id is None:
            branch_id = Branch.current().id
        if turn_id is None:
            turn_id = Turn.current().id
        if span_id is None:
            span_id = ExecutionSpan.current().id
        
        return await insert_block(block, branch_id, turn_id, span_id)
    
    