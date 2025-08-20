import asyncio
import asyncpg
import hashlib
import json
import uuid
from typing import Any, Dict, List, Optional
from promptview.block.block7 import BaseBlock, Block, BlockList, BlockSent
from promptview.utils.db_connections import PGConnectionManager
import datetime as dt

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



# async def insert_block_tree(block: Block, branch_id: int, turn_id: int) -> str:
    # root_data = block_to_dict(block)
async def insert_block_tree2(root_data: Dict[str, Any], branch_id: int, turn_id: int) -> str:
    async with PGConnectionManager.transaction() as tx:
        tree_id = str(uuid.uuid4())
        created_at = dt.datetime.now()
        await tx.execute("INSERT INTO block_trees (id, created_at, branch_id, turn_id) VALUES ($1, $2, $3, $4)", tree_id, created_at, branch_id, turn_id)

        nodes = flatten_tree(root_data)

        # --- prepare rows ---
        block_rows = []
        node_rows = []

        for node in nodes:
            blk_id = block_hash(node["content"], node["json_content"])
            block_rows.append((blk_id, node["content"], json.dumps(node["json_content"])))
            node_rows.append((tree_id, node["path"], blk_id, json.dumps(node["style"])))

        # --- bulk insert blocks ---
        await tx.execute("""
            INSERT INTO blocks (id, content, json_content)
            SELECT x.id, x.content, x.json_content
            FROM UNNEST($1::text[], $2::text[], $3::jsonb[]) AS x(id, content, json_content)
            ON CONFLICT (id) DO NOTHING
        """,
        [r[0] for r in block_rows],
        [r[1] for r in block_rows],
        [r[2] for r in block_rows])

        # --- bulk insert nodes ---
        await tx.execute("""
            INSERT INTO block_nodes (tree_id, path, block_id, style)
            SELECT x.tree_id, x.path::ltree, x.block_id, x.style
            FROM UNNEST($1::uuid[], $2::text[], $3::text[], $4::jsonb[]) 
                    AS x(tree_id, path, block_id, style)
        """,
        [r[0] for r in node_rows],
        [r[1] for r in node_rows],
        [r[2] for r in node_rows],
        [r[3] for r in node_rows])

        return tree_id


def get_real_parent(n: BaseBlock) -> Block:
    parent = n.parent
    if isinstance(parent, Block):
        return parent
    elif isinstance(n.parent, BlockList):
        return get_real_parent(parent)
    elif isinstance(parent, BlockSent):
        return get_real_parent(parent)
    else:
        raise ValueError(f"Unknown parent type: {type(parent)}")
        
        
        
        
    
        

def block_to_dict(block: Block) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    block_sent_dumps = []
    blocks_dumps = []
    used_nodes = set()
    for n in block.traverse():
        parent = get_real_parent(n)
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
            "content": n.render(),
            "json_content": n.model_dump(),
        }
        
        
        block_sent_dumps.append(d)
    return block_sent_dumps, blocks_dumps



async def insert_block_tree(block: Block, branch_id: int, turn_id: int) -> str:
    nodes, blocks = block_to_dict(block)
    async with PGConnectionManager.transaction() as tx:
        tree_id = str(uuid.uuid4())
        created_at = dt.datetime.now()
        await tx.execute("INSERT INTO block_trees (id, created_at, branch_id, turn_id) VALUES ($1, $2, $3, $4)", tree_id, created_at, branch_id, turn_id)

        # nodes = flatten_tree(root_data)

        # --- prepare rows ---
        block_rows = []
        node_rows = []

        for node in nodes:
            blk_id = block_hash(node["content"], node["json_content"])
            block_rows.append((blk_id, node["content"], json.dumps(node["json_content"])))
            # node_rows.append((tree_id, node["path"], blk_id, json.dumps(node["style"])))
            node_rows.append((tree_id, node["path"], blk_id, json.dumps({})))

        # --- bulk insert blocks ---
        await tx.execute("""
            INSERT INTO blocks (id, content, json_content)
            SELECT x.id, x.content, x.json_content
            FROM UNNEST($1::text[], $2::text[], $3::jsonb[]) AS x(id, content, json_content)
            ON CONFLICT (id) DO NOTHING
        """,
        [r[0] for r in block_rows],
        [r[1] for r in block_rows],
        [r[2] for r in block_rows])

        # --- bulk insert nodes ---
        await tx.execute("""
            INSERT INTO block_nodes (tree_id, path, block_id, style)
            SELECT x.tree_id, x.path::ltree, x.block_id, x.style
            FROM UNNEST($1::uuid[], $2::text[], $3::text[], $4::jsonb[]) 
                    AS x(tree_id, path, block_id, style)
        """,
        [r[0] for r in node_rows],
        [r[1] for r in node_rows],
        [r[2] for r in node_rows],
        [r[3] for r in node_rows])

        return tree_id



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
