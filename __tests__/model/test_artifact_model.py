





import datetime as dt
from typing import List

import pytest_asyncio
from promptview.model2 import Model, ModelField, KeyField, RelationField
from promptview.model2 import NamespaceManager
from promptview.model2 import Turn
from promptview.model2 import ArtifactModel
from promptview.model2.version_control_models import Branch


class Like(ArtifactModel):
    post_id: int = ModelField(foreign_key=True)    

class Post(ArtifactModel):
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











@pytest_asyncio.fixture()
async def seeded_database(clean_database):
    user = await User(name="John", age=30).save()
    branch = await Branch.query().filter(lambda b: b.id == 1).last()
        

    yield {

    }








@pytest.mark.asyncio
async def test_artifact_model_basic(seeded_database):
    user = seeded_database["user"]
    branch = seeded_database["branch"]
    branch2 = seeded_database["branch2"]

