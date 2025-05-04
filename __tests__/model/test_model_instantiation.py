import pytest
import pytest_asyncio

import datetime as dt
from typing import List
from promptview.model2 import Model, ModelField, KeyField, RelationField
from promptview.model2 import NamespaceManager
from promptview.model2 import Turn, TurnModel, Branch
from __tests__.utils import clean_database, test_db_pool
from promptview.model2.version_control_models import VersioningError

class Like(TurnModel):
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    post_id: int = ModelField(foreign_key=True)    

class Post(TurnModel):
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    title: str = ModelField()
    content: str = ModelField()
    likes: List[Like] = RelationField(foreign_key="post_id")
    user_id: int = ModelField(foreign_key=True)


class User(Model):
    id: int = KeyField(primary_key=True)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    name: str = ModelField()
    age: int = ModelField()
    address: str = ModelField()
    posts: List[Post] = RelationField(foreign_key="user_id")









@pytest.mark.asyncio
async def test_turn_model_error_when_no_turn_id_is_provided(clean_database):
    user = await User(name="Test", age=30, address="Test").save()
    with pytest.raises(VersioningError):
        await Post(title="Test", content="Test", user_id=user.id).save()
    with pytest.raises(VersioningError):
        await user.add(Post(title="Test", content="Test"))



