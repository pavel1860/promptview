





import datetime as dt
from typing import List, Literal
from uuid import uuid4


import pytest
import pytest_asyncio

from promptview.model2 import Model, ModelField, KeyField, RelationField, Relation
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
    likes: Relation[Like] = RelationField(foreign_key="post_id")
    user_id: int = ModelField(foreign_key=True)







class Message(ArtifactModel):
    content: str = ModelField(default="")
    name: str | None = ModelField(default=None)    
    role: Literal["user", "assistant", "system", "tool"] = ModelField(default="user")
    


class Turn(BaseTurn):
    user_id: int = ModelField(foreign_key=True)
    messages: Relation[Message] = RelationField(foreign_key="turn_id")
    posts: Relation[Post] = RelationField(foreign_key="turn_id")
    likes: Relation[Like] = RelationField(foreign_key="turn_id")


class User(Model):
    id: int = KeyField(primary_key=True)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    name: str = ModelField()
    age: int = ModelField()
    address: str = ModelField()
    posts: Relation[Post] = RelationField(foreign_key="user_id")
    turns: Relation[Turn] = RelationField(foreign_key="user_id")


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
    with user:
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
    with user:
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
        
            


@pytest.mark.asyncio
async def test_multi_user_artifact_model(clean_database):
    user1 = await User(name="John Doe", age=10, address="test" ).save()
    user2 = await User(name="Smith Black", age=20, address="test" ).save()
    user3 = await User(name="Red Shield", age=30, address="test" ).save()
    
    branch = await Branch.get(1)
    with user1:    
        with branch:    
            async with Turn.start() as turn1:
                b1_t1_message1 = await turn1.add(Message(content="Hello"))
                b1_t1_message2 = await turn1.add(Message(content="Hello, John Doe! world!", role="assistant"))
            
            async with Turn.start() as turn2:
                b1_t2_message1 = await turn2.add(Message(content="Who are you?"))
                b1_t2_message2 = await turn2.add(Message(content="I'm a helpful assistant John Doe.", role="assistant"))
            
            async with Turn.start() as turn3:
                b1_t3_message1 = await turn3.add(Message(content="What is the capital of France?"))
                b1_t3_message2 = await turn3.add(Message(content="Paris is the capital of France.", role="assistant"))

        async with branch.fork(turn=turn2) as branch2_1:
            async with Turn.start() as turn21:
                b2_t1_message1 = await turn21.add(Message(content="What is the capital of Italy?"))
                b2_t1_message2 = await turn21.add(Message(content="Rome is the capital of Italy.", role="assistant"))
            
    with user2:    
        with branch:    
            async with Turn.start() as turn1:
                b1_t1_message1 = await turn1.add(Message(content="Hello"))
                b1_t1_message2 = await turn1.add(Message(content="Hello, world Smith Black!", role="assistant"))
            
            async with Turn.start() as turn2:
                b1_t2_message1 = await turn2.add(Message(content="Who are you?"))
                b1_t2_message2 = await turn2.add(Message(content="I'm a helpful assistant Smith Black.", role="assistant"))
            
            async with Turn.start() as turn3:
                b1_t3_message1 = await turn3.add(Message(content="What is the best vagitable?"))
                b1_t3_message2 = await turn3.add(Message(content="The best vagitable is tomato.", role="assistant"))

        async with branch.fork(turn=turn2) as branch2_2:            
            async with Turn.start() as turn21:
                b2_t1_message1 = await turn21.add(Message(content="What is the best fruit?"))
                b2_t1_message2 = await turn21.add(Message(content="The best fruit is apple.", role="assistant"))
                

    with user3:    
        with branch:    
            async with Turn.start() as turn1:
                b1_t1_message1 = await turn1.add(Message(content="Hello"))
                b1_t1_message2 = await turn1.add(Message(content="Hello, world Red Shield!", role="assistant"))
            
            async with Turn.start() as turn2:
                b1_t2_message1 = await turn2.add(Message(content="Who are you?"))
                b1_t2_message2 = await turn2.add(Message(content="I'm a helpful assistant Red Shield.", role="assistant"))
            
            async with Turn.start() as turn3:
                b1_t3_message1 = await turn3.add(Message(content="What is Quantom physics?"))
                b1_t3_message2 = await turn3.add(Message(content="Quantom physics is a branch of physics that studies the behavior of matter and energy at the smallest scales.", role="assistant"))

        async with branch.fork(turn=turn2) as branch2_3:
            async with Turn.start() as turn21:
                b2_t1_message1 = await turn21.add(Message(content="What is the Theory of Relativity?"))
                b2_t1_message2 = await turn21.add(Message(content="The Theory of Relativity is a theory of physics that describes the relationship between space and time.", role="assistant"))
                
                
    with user1:    
        with branch:    
            messages = await Message.query().order_by("created_at").limit(10)
            assert len(messages) == 6
            assert messages[0].content == "Hello"
            assert messages[1].content == "Hello, John Doe! world!"
            assert messages[2].content == "Who are you?"
            assert messages[3].content == "I'm a helpful assistant John Doe."
            assert messages[4].content == "What is the capital of France?"
            assert messages[5].content == "Paris is the capital of France."
        
        
                
                
                
                
                