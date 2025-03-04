import os
os.environ["POSTGRES_URL"] = "postgresql://snack:Aa123456@localhost:5432/promptview_test"
import pytest
import pytest_asyncio
import datetime as dt
from promptview.model.fields import ModelField, IndexType, ModelRelation
from promptview.model.model import Model, Relation
from promptview.model.resource_manager import connection_manager
from promptview.model.vectors.openai_vectorizer import OpenAISmallVectorizer
from promptview.model.postgres_client import PostgresClient




class Post(Model):
    title: str = ModelField()
    content: str = ModelField()
    user_id: int = ModelField(default=None)
    
    class Config:
        database_type = "postgres"


class User(Model):
    name: str = ModelField()
    age: int = ModelField()
    posts: Post = ModelRelation(key="user_id")
    
    class Config:
        database_type = "postgres"


    
    
    
    

@pytest_asyncio.fixture()
async def seeded_database():
    # Create and seed test data
    
    await connection_manager.init_all_namespaces()

    user1 = await User(name="John Doe 1", age=30).save()
    user2 = await User(name="Jane Doe 2", age=25).save()
    
    # post1 = Post(title="Post 1", content="Content 1", user_id=user1.id)
    # post2 = Post(title="Post 2", content="Content 2", user_id=user1.id)
    # post3 = Post(title="Post 3", content="Content 3", user_id=user2.id)
    
    await user1.posts.add(Post(title="Post 1", content="Content 1"))
    await user1.posts.add(Post(title="Post 2", content="Content 2"))
    await user2.posts.add(Post(title="Post 3", content="Content 3"))
    
    # await Post.batch_upsert([post1, post2, post3])
    
    yield connection_manager
    
    await connection_manager.drop_all_namespaces()
    
    
    
@pytest.mark.asyncio
async def test_seperate_query(seeded_database):
    user = await User.get(1)
    assert user is not None
    assert user.name == "John Doe 1"
    # posts = await user.posts.all()
    # assert len(posts) == 2
    # assert posts[0].title == "Post 1"
    # assert posts[1].title == "Post 2"
