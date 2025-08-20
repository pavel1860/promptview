from promptview.model3 import Model, VersionedModel, KeyField, ModelField, RelationField, Branch, Turn
from promptview.model3 import NamespaceManager
import datetime as dt
from uuid import UUID
from typing import List


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
    block_id: str = ModelField(foreign_key=True)
    style: dict | None = ModelField(default=None)
    role: str | None = ModelField(default=None)
    order_in_parent: int = ModelField(default=0)
    tree: "BlockTree" = RelationField(primary_key="tree_id", foreign_key="id")



class BlockTree(VersionedModel):
    id: UUID = KeyField(primary_key=True)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    nodes: List["BlockNode"] = RelationField(foreign_key="tree_id")
    
    


