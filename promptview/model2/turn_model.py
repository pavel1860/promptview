
from promptview.model2.model import Model, MODEL
from promptview.model2.fields import KeyField, ModelField
from promptview.model2.namespace_manager import NamespaceManager
from promptview.model2.version_control_models import Turn, Branch
import uuid
import datetime as dt
from typing import Type




class TurnModel(Model):
    id: int = KeyField(primary_key=True)    
    branch_id: int = ModelField(foreign_key=True)
    turn_id: int = ModelField(foreign_key=True)    
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    updated_at: dt.datetime | None = ModelField(default=None)
    deleted_at: dt.datetime | None = ModelField(default=None)




