





import datetime as dt
from typing import List, Literal


import pytest
import pytest_asyncio

from promptview.model2 import Model, ModelField, KeyField, RelationField
from promptview.model2 import NamespaceManager
from promptview.model2 import Turn as BaseTurn
from promptview.model2 import ArtifactModel
from promptview.model2.version_control_models import Branch
from __tests__.utils import clean_database, test_db_pool

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




class Message(ArtifactModel):
    content: str = ModelField(default="")
    name: str | None = ModelField(default=None)    
    role: Literal["user", "assistant", "system", "tool"] = ModelField(default="user")
    


class Turn(BaseTurn):
    messages: List[Message] = RelationField(foreign_key="turn_id")
    posts: List[Post] = RelationField(foreign_key="turn_id")
    likes: List[Like] = RelationField(foreign_key="turn_id")





@pytest_asyncio.fixture()
async def seeded_database(clean_database):
    user = await User(name="John", age=30).save()
    branch = await Branch.query().filter(lambda b: b.id == 1).last()
    
        

    yield {

    }








@pytest.mark.asyncio
async def test_artifact_model_basic(clean_database):
    
    user = await User(name="test", age=10, address="test").save()
    branch = await Branch.get(1)
    with branch:
        async with Turn.start():
            post1 = await user.add(Post(title="post 1", content="content 1"))
            
        async with Turn.start():
            post2 = await user.add(Post(title="post 2", content="content 2"))
                
        async with Turn.start():
            post1.content = "content 1 updated"
            await post1.save()


    posts = await Post.query().order_by("-created_at")
    assert len(posts) == 2
    assert posts[1].content == "content 1 updated"
    assert posts[0].content == "content 2"



@pytest.mark.asyncio
async def test_artifact_model_order_by(clean_database):
    user = await User(name="test", age=10, address="test").save()
    branch = await Branch.get(1)
    with branch:
        async with Turn.start():
            post1 = await user.add(Post(title="post 1", content="content 1"))
        async with Turn.start():
            post2 = await user.add(Post(title="post 2", content="content 2"))
        async with Turn.start():
            post1.content = "content 1 updated 1"
            await post1.save()
        async with Turn.start():
            post3 = await user.add(Post(title="post 3", content="content 3"))
            post2.content = "content 2 updated 1"
            await post2.save()
            post1.content = "content 1 updated 2"
            await post1.save()
        async with Turn.start():
            post1.content = "content 1 updated 3"
            await post1.save()
            
            
    posts = await Post.query().order_by("created_at")
    assert len(posts) == 3
    assert posts[0].content == "content 1 updated 3"
    assert posts[1].content == "content 2 updated 1"
    assert posts[2].content == "content 3"


    posts = await Post.query().order_by("-created_at")
    assert len(posts) == 3
    assert posts[2].content == "content 1 updated 3"
    assert posts[1].content == "content 2 updated 1"
    assert posts[0].content == "content 3"
    
    
    
    
@pytest.mark.asyncio
async def test_artifact_ordering(clean_database):
    user = await User(name="test", age=10, address="test").save()
    branch = await Branch.query().where(id=1).last()
    with user:    
        with branch:    
            async with Turn.start() as turn1:
                b1_t1_message1 = await turn1.add(Message(content="Hello"))
                b1_t1_message2 = await turn1.add(Message(content="Hello, world!", role="assistant"))
            
            async with Turn.start() as turn2:
                b1_t2_message1 = await turn2.add(Message(content="Who are you?"))
                b1_t2_message2 = await turn2.add(Message(content="I'm a helpful assistant.", role="assistant"))
            
            async with Turn.start() as turn3:
                b1_t3_message1 = await turn3.add(Message(content="What is the capital of France?"))
                b1_t3_message2 = await turn3.add(Message(content="Paris is the capital of France.", role="assistant"))

        branch2 = await branch.fork(turn=turn2)
        with branch2:            
                async with Turn.start() as turn21:
                    b2_t1_message1 = await turn21.add(Message(content="What is the capital of Italy?"))
                    b2_t1_message2 = await turn21.add(Message(content="Rome is the capital of Italy.", role="assistant"))  
        
        with branch:       
            msgs = await Message.query(turns=2).order_by("created_at")
            assert len(msgs) == 4
            msgs = await Message.query(turns=1).order_by("created_at")
            assert len(msgs) == 2
            msgs = await Message.query(turns=3).order_by("created_at")
            assert len(msgs) == 6
            assert msgs[0].id == b1_t1_message1.id
            assert msgs[1].id == b1_t1_message2.id
            assert msgs[2].id == b1_t2_message1.id
            assert msgs[3].id == b1_t2_message2.id
            assert msgs[4].id == b1_t3_message1.id
            assert msgs[5].id == b1_t3_message2.id
            
            
        with branch2:
            msgs = await Message.query(turns=2).order_by("created_at")
            assert len(msgs) == 4
            msgs = await Message.query(turns=1).order_by("created_at")
            assert len(msgs) == 2
            msgs = await Message.query(turns=3).order_by("created_at")
            assert len(msgs) == 6
            assert msgs[0].id == b1_t1_message1.id
            assert msgs[1].id == b1_t1_message2.id
            assert msgs[2].id == b1_t2_message1.id
            assert msgs[3].id == b1_t2_message2.id
            assert msgs[4].id == b2_t1_message1.id
            assert msgs[5].id == b2_t1_message2.id
        
            
        