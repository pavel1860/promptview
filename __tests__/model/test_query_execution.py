import os
import uuid


os.environ["POSTGRES_URL"] = "postgresql://ziggi:Aa123456@localhost:5432/promptview_test"

import pytest
import pytest_asyncio

import datetime as dt
from typing import List
from promptview.model2 import Model, ModelField, KeyField, RelationField
from promptview.model2.postgres.query_set3 import SelectQuerySet
from promptview.model2 import NamespaceManager


class Like(Model):
    id: int = KeyField(primary_key=True)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    post_id: int = ModelField(foreign_key=True)    

class Post(Model):
    id: int = KeyField(primary_key=True)
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


@pytest_asyncio.fixture()
async def seeded_database():
    await NamespaceManager.create_all_namespaces()
    user = await User(name="test", age=10, address="test").save()
    post1 = await user.add(Post(title="post 1", content="content 1"))
    p1_like1 = await post1.add(Like(post_id=post1.id))
    p1_like2 = await post1.add(Like(post_id=post1.id))
    post2 = await user.add(Post(title="post 2", content="content 2"))
    p2_like1 = await post2.add(Like(post_id=post2.id))
    p2_like2 = await post2.add(Like(post_id=post2.id))
    yield {
        "user": user,
        "post1": post1,
        "p1_like1": p1_like1,
        "p1_like2": p1_like2,
        "post2": post2,
        "p2_like1": p2_like1,
        "p2_like2": p2_like2,
    }
    await NamespaceManager.drop_all_namespaces()




@pytest.mark.asyncio
async def test_query_builders(seeded_database):
    user = seeded_database["user"]
    post1 = seeded_database["post1"]
    p1_like1 = seeded_database["p1_like1"]
    p1_like2 = seeded_database["p1_like2"]
    post2 = seeded_database["post2"]
    
    # query = SelectQuerySet(User).alias("u").select("*").join(Post).select("*").alias("p").join(Like).select("*").alias("l")
    l_query = SelectQuerySet(Like).select("*")
    p_query = SelectQuerySet(Post).select("*").join(l_query)
    query = SelectQuerySet(User).select("*").join(p_query)

    print(query.render())
    users = await query.execute()
    users[0].posts[1].likes

    assert len(users) == 1
    assert len(users[0].posts) == 2
    assert len(users[0].posts[0].likes) == 2
    assert len(users[0].posts[1].likes) == 2

    

