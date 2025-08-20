from promptview.model3.model3 import Model
from promptview.model3.versioning.models import VersionedModel
from promptview.model3.fields import KeyField, ModelField, RelationField
import datetime as dt
from uuid import UUID
from typing import List

from promptview.model3.sql.expressions import RawValue
from promptview.model3.sql.queries import Column


class BlockModel(Model):
    _namespace_name: str = "blocks"
    id: str = KeyField(primary_key=True)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    content: str | None = ModelField(default=None)
    json_content: dict | None = ModelField(default=None)    
    

class BlockNode(Model):
    id: int = KeyField(primary_key=True)
    tree_id: UUID = ModelField(foreign_key=True)
    path: str = ModelField(db_type="LTREE")
    type: str = ModelField()
    block_id: str = ModelField(foreign_key=True)
    styles: list[str] | None = ModelField(default=None)
    role: str | None = ModelField(default=None)
    order_in_parent: int = ModelField(default=0)
    tags: list[str] | None = ModelField(default=None)
    attrs: dict | None = ModelField(default=None)
    tree: "BlockTree" = RelationField(primary_key="tree_id", foreign_key="id")
    
    @classmethod
    async def block_query(cls, cte):
        from promptview.model3.block_models.block_log import pack_block
        records = await cls.query([
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
        .where(lambda b: (b.tree_id == RawValue("btc.id"))).print().json()
        return pack_block(records)



class BlockTree(VersionedModel):
    id: UUID = KeyField(primary_key=True)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    nodes: List["BlockNode"] = RelationField(foreign_key="tree_id")
    
    

    
