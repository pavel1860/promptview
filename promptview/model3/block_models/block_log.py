import asyncio
import asyncpg
import hashlib
import json
import uuid
from typing import Any, Dict, List, Optional
from promptview.block.block7 import BaseBlock, Block, BlockChunk, BlockList, BlockSent
from promptview.model.versioning import Branch
from promptview.model3.sql.expressions import RawValue
from promptview.model3.sql.queries import Column
from promptview.utils.db_connections import PGConnectionManager
import datetime as dt
# from promptview.model3.block_models.block_models import BlockNode, BlockModel
from promptview.model3.versioning.models import BlockTree, BlockNode, BlockModel

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





def get_real_parent(n: BaseBlock) -> tuple[Block, str]:
    parent = n.parent
    if parent is None and n.path != [1]:
        raise ValueError(f"Node {n} has no parent")
    if isinstance(parent, Block):
        return parent, "root"
    elif isinstance(parent, BlockList):
        parent, _ =  get_real_parent(parent)
        return parent, "child"
    elif isinstance(parent, BlockSent):
        raise ValueError(f"BlockSent {parent} has no parent")
        # parent = get_real_parent(parent)
    else:
        raise ValueError(f"Unknown parent type: {type(parent)}")
        
        
        
        
    
        

def block_to_dict(block: Block) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    block_sent_dumps = []
    blocks_dumps = []
    used_nodes = set()
    for n in block.traverse():
        parent, _type = get_real_parent(n)
        ppath = ".".join(str(p) for p in parent.path)
        if ppath not in used_nodes:
            blocks_dumps.append({
                "path": ppath,
                "styles": parent.styles,
                "role": parent.role,
                "tags": parent.tags,
                "attrs": parent.attrs,
                "index": parent.id,                
            })
        d = {
            "path": ".".join(str(p) for p in n.path),
            "type": _type,
            "content": n.render(),
            "json_content": n.model_dump(),            
            # Block fields
            "styles": parent.styles,
            "role": parent.role,
            "tags": parent.tags,
            "attrs": parent.attrs,
            "index": parent.id,
        }
        
        
        block_sent_dumps.append(d)
    return block_sent_dumps, blocks_dumps



async def insert_block(block: Block, index: int, branch_id: int, turn_id: int, span_id: uuid.UUID | None = None) -> str:
    """
    Alternative implementation using executemany for bulk inserts.
    This approach is cleaner and more straightforward than UNNEST.
    """
    nodes, blocks = block_to_dict(block)
    async with PGConnectionManager.transaction() as tx:
        tree_id = str(uuid.uuid4())
        created_at = dt.datetime.now()
        await tx.execute(
            "INSERT INTO block_trees (id, created_at, branch_id, turn_id, span_id, index) VALUES ($1, $2, $3, $4, $5, $6)", 
            tree_id, created_at, branch_id, turn_id, span_id, index
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
                node["type"],
                styles_array, 
                node["role"], 
                tags_array, 
                json.dumps(node["attrs"])
            ))

        # --- bulk insert nodes using executemany ---
        if node_rows:
            await tx.executemany(
                "INSERT INTO block_nodes (tree_id, path, block_id, type, styles, role, tags, attrs) VALUES ($1, $2::ltree, $3, $4, $5, $6, $7, $8)",
                node_rows
            )

        return tree_id


# Example usage and testing function
async def test_executemany_vs_unnest(block: Block, branch_id: int, turn_id: int):
    """
    Test function to compare executemany vs UNNEST approaches.
    This can be used to benchmark and validate both implementations.
    """
    import time
    
    # Test executemany approach
    start_time = time.time()
    tree_id_executemany = await insert_block(block, branch_id, turn_id)
    executemany_time = time.time() - start_time
    
    # Test UNNEST approach  
    start_time = time.time()
    tree_id_unnest = await insert_block_tree(block, branch_id, turn_id + 1)  # Use different turn_id
    unnest_time = time.time() - start_time
    
    print(f"ExecuteMany time: {executemany_time:.4f}s, Tree ID: {tree_id_executemany}")
    print(f"UNNEST time: {unnest_time:.4f}s, Tree ID: {tree_id_unnest}")
    
    return {
        "executemany": {"time": executemany_time, "tree_id": tree_id_executemany},
        "unnest": {"time": unnest_time, "tree_id": tree_id_unnest}
    }


async def fetch_block_nodes(tree_id: str, conn):
    rows = await conn.fetch("""
        SELECT 
            bn.path::text AS path,
            b.content,
            b.json_content,
            bn.style,
            bn.tags,
            bn.role
        FROM block_nodes bn
        JOIN blocks b ON b.id = bn.block_id
        WHERE bn.tree_id = $1
        ORDER BY bn.path;
    """, tree_id)
    return [dict(r) for r in rows]



async def load_cert_chain(branch: Branch, tree_id: str) -> list[dict]:
    with branch:
        res = await BlockNode.query([
                Column("tree_id", "btc"),
                Column("styles", "bn"),
                Column("role", "bn"),
                Column("tags", "bn"),
                Column("path", "bn"),
                Column("attrs", "bn"),
                Column("type", "bn"),
                Column("content", "bsm"),
                Column("json_content", "bsm"),            
            ], alias="bn") \
            .use_cte(
                BlockTree.query(alias="bt").select("*") \
                .where(lambda b: (b.id == tree_id)) \
            ,"tree_cte", alias="btc") \
            .join(BlockModel.query(["content", "json_content"], alias="bsm"), on=("block_id", "id")) \
            .where(lambda b: (b.tree_id == RawValue("btc.id"))).print().json()
        return res
    
    
def _build_block_tree_query(cte):
    return BlockNode.query([
        Column("tree_id", "btc"),
        Column("styles", "bn"),
        Column("role", "bn"),
        Column("tags", "bn"),
        Column("path", "bn"),
        Column("attrs", "bn"),
        Column("type", "bn"),
        Column("content", "bsm"),
        Column("json_content", "bsm"),            
    ], alias="bn") \
    .use_cte(cte,"tree_cte", alias="btc") \
    .join(BlockModel.query(["content", "json_content"], alias="bsm"), on=("block_id", "id")) \
    .where(lambda b: (b.tree_id == RawValue("btc.id")))


async def get_many_block_trees(cte):
    query = _build_block_tree_query(cte)
    records = await query.json()
    curr_tree_id = None
    target_records = []
    for rec in records:
        if rec["tree_id"] != curr_tree_id:
            curr_tree_id = rec["tree_id"]
            pack_block(target_records)
            target_records = []
        
    
    

    
    

def pack_block(records: list[dict]) -> Block:
    block_lookup = {}

    def build_sentence(rec: dict) -> BlockSent:
        sent = BlockSent()   
        json_content = rec["json_content"]
        for c in json_content["blocks"]:
            chunk = BlockChunk(
                index=c["index"],
                content=c["content"],
                logprob=c.get("logprob", None),            
            )
            sent.append(chunk)
        return sent

    for rec in records:
        path_str = rec["path"]
        path = path_str.split(".")
        if rec["type"] == "root":
            block = Block(
                styles=rec["styles"],
                role=rec["role"],
                tags=rec["tags"],
                attrs=rec["attrs"],
            )
            sent = build_sentence(rec)
            block.root = sent
            block_lookup[path_str] = block
            if len(path) > 1:
                parent = block_lookup[path_str[:-2]]
                parent.children.append(block)
        else:
            block = block_lookup[path_str[:-2]]
            sent = build_sentence(rec)
            block.children.append(sent)
    block = block_lookup["1"]    
    return block
        
    
    
    
async def load_block_tree(branch: Branch, tree_id: str) -> Block:
    records = await load_cert_chain(branch, tree_id)
    return pack_block(records)
    



def parse_block_tree_json(block_tree: dict, model_dump: bool = True) -> Block:
    print(">", block_tree)
    block_lookup: dict[str, Block] = {}
    def build_sentence(node: dict) -> BlockSent:
        sj = node["block"]["json_content"]
        sj['_type'] = "BlockSent"
        sent = BlockSent.model_validate(sj)           
        return sent


    for node in block_tree["nodes"]:
        path_str = node["path"]
        path = path_str.split(".")
        if node["type"] == "root":
            block = Block(
                styles=node["styles"],
                role=node["role"],
                tags=node["tags"],
                attrs=node["attrs"],
            )
            sent = build_sentence(node)
            block.root = sent
            block_lookup[path_str] = block
            if len(path) > 1:
                parent = block_lookup[path_str[:-2]]
                parent.children.append(block)
        else:
            block = block_lookup[path_str[:-2]]
            sent = build_sentence(node)
            block.children.append(sent)
    block = block_lookup["0"] 
    if model_dump:
        return block.model_dump()
    return block


def parse_turn_spans_json(turn):
    span_lookup = {}
    root_span = None
    for span in turn['spans']:
        if span['parent_span_id'] is None:
            if root_span is not None:
                raise ValueError("Multiple root spans found")
            root_span = span
        span['children'] = []
        span_lookup[span['id']] = span
        block_list = [(block_tree['index'], parse_block_tree_json(block_tree)) for block_tree in span["block_trees"]]
        for b in block_list:
            span['children'].append({'type': 'block', 'data': b[1].model_dump(), 'index': b[0]})
        del span['block_trees']
    
    for span in turn['spans']:
        if span['parent_span_id'] is not None:
            parent = span_lookup[span['parent_span_id']]
            parent['children'].append({'type': 'span', 'data': span, 'index': span['index']})

    for span in turn['spans']:
        span['children'].sort(key=lambda x: x['index'])
        
    del turn['spans']
    turn['span'] = root_span
    return turn
        
        
    
    
def parse_turn_spans_json2(turn):

    for span in turn['spans']:
        span["block_trees"].sort(key=lambda x: x['created_at'])
        block_list = [parse_block_tree_json(block_tree) for block_tree in span["block_trees"]]
        span['blocks'] = BlockList(block_list).model_dump()
        del span['block_trees']    
    turn['spans'].sort(key=lambda x: x['start_time'])
    return turn
   
    
    
    
def parse_block_tree(block_tree: BlockTree) -> Block:
    print(">", block_tree)
    block_lookup: dict[str, Block] = {}
    def build_sentence(node: BlockNode) -> BlockSent:
        sent = BlockSent()   
        json_content = node.block.json_content
        for c in json_content["children"]:
            chunk = BlockChunk(
                index=c["index"],
                content=c["content"],
                logprob=c.get("logprob", None),            
            )
            sent.append(chunk)
        return sent


    for node in block_tree.nodes:
        path_str = node.path
        path = path_str.split(".")
        if node.type == "root":
            block = Block(
                styles=node.styles,
                role=node.role,
                tags=node.tags,
                attrs=node.attrs,
            )
            sent = build_sentence(node)
            block.root = sent
            block_lookup[path_str] = block
            if len(path) > 1:
                parent = block_lookup[path_str[:-2]]
                parent.children.append(block)
        else:
            block = block_lookup[path_str[:-2]]
            sent = build_sentence(node)
            block.children.append(sent)
    block = block_lookup["1"]    
    return block


def parse_block_tree_turn(turn):
    block_list = [parse_block_tree(block_tree) for block_tree in turn.block_tree]
    return BlockList(block_list)
