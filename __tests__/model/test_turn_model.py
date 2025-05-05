import os
import uuid
os.environ["POSTGRES_URL"] = "postgresql://ziggi:Aa123456@localhost:5432/promptview_test"

import pytest
import pytest_asyncio

from enum import StrEnum
from typing import TYPE_CHECKING, Any, List, Literal, Type
from uuid import UUID

from pydantic import BaseModel, Field
from promptview.auth.user_manager import AuthModel
from promptview.model2 import Model, ArtifactModel, ModelField, RelationField, ArtifactModel
import datetime as dt
from promptview.model2.fields import KeyField, RelationField, ModelField
from promptview.model2.namespace_manager import NamespaceManager
from promptview.prompt import Block, ToolCall


    




from enum import StrEnum
from typing import TYPE_CHECKING, Any, List, Literal, Type
from uuid import UUID

from pydantic import BaseModel, Field
from promptview.auth.user_manager import AuthModel
from promptview.model2 import Model, ArtifactModel, ModelField, RelationField, ArtifactModel
import datetime as dt
from promptview.model2.namespace_manager import NamespaceManager
from promptview.prompt import Block, ToolCall
from promptview.model2.version_control_models import Turn, Branch
from promptview.model2 import TurnModel

from __tests__.utils import clean_database, test_db_pool


    
    


class LikeType(StrEnum):
    LIKE = "like"
    DISLIKE = "dislike"

# model_cls = Model
model_cls = ArtifactModel


class Like(TurnModel):    
    type: LikeType = ModelField()
    user_id: int = ModelField(foreign_key=True)
    comment_id: int = ModelField(foreign_key=True)
    

class Comment(TurnModel):    
    content: str = ModelField()
    reliability: float = ModelField(default=0.5)
    user_id: int = ModelField(foreign_key=True)
    post_id: int = ModelField(foreign_key=True)
    likes: List[Like] = RelationField([], foreign_key="comment_id")    


class Post(TurnModel):    
    title: str = ModelField()
    content: str = ModelField()
    owner_id: int = ModelField(foreign_key=True)
    comments: List[Comment] = RelationField([], foreign_key="post_id")
    



class Message(TurnModel):
    content: str = ModelField(default="")
    name: str | None = ModelField(default=None)
    sender_id: int | None = ModelField(default=None)    
    role: Literal["user", "assistant", "system", "tool"] = ModelField(default="user")
    platform_id: str | None = ModelField(default=None)
    tool_calls: List[ToolCall] = ModelField(default=[])
    model: str | None = ModelField(default=None)
    run_id: str | None = ModelField(default=None)      
    
        
    def _payload_dump(self, *args, **kwargs):
        res = super()._payload_dump(*args, **kwargs)
        if self.tool_calls:
            res["tool_calls"] = [tool.model_dump() for tool in self.tool_calls]
        return res
        
    def block(self) -> Block:
        tags = []
        if self.role == "user":
            tags = ["user_input"]
        elif self.role == "assistant":
            tags = ["generation"]
        elif self.role == "tool":
            tags = ["tool"]
        else:
            raise ValueError("Invalid role")
        return Block(
            content=self.content,
            role=self.role,
            tags=tags,
            id=self.platform_id,
            tool_calls=self.tool_calls,
            model=self.model,
            run_id=self.run_id,
        )



class User(Model):
    id: int = KeyField(primary_key=True)
    # name: str = ModelField()
    age: int = ModelField()
    posts: List[Post] = RelationField([], foreign_key="owner_id")
    likes: List[Like] = RelationField([], foreign_key="user_id")
    comments: List[Comment] = RelationField([], foreign_key="user_id")
    







@pytest_asyncio.fixture()
async def seeded_database(clean_database):
    user = await User(name="John", age=30).save()
    branch = await Branch.query().filter(lambda b: b.id == 1).last()
    
    with user:
        with branch:
        
            async with Turn.start() as turn1:
                b1_t1_message1 = await turn1.add(Message(content="Hello"))
                b1_t1_message2 = await turn1.add(Message(content="Hello, world!", role="assistant"))
            
            async with Turn.start() as turn2:
                b1_t2_message1 = await turn2.add(Message(content="Who are you?"))
                b1_t2_message2 = await turn2.add(Message(content="I'm a helpful assistant."))
            
            async with Turn.start() as turn3:
                b1_t3_message1 = await turn3.add(Message(content="What is the capital of France?"))
                b1_t3_message2 = await turn3.add(Message(content="Paris is the capital of France."))


        branch2 = await branch.fork(turn=turn2)
        with branch2:
            async with Turn.start() as turn21:
                b2_t1_message1 = await turn21.add(Message(content="What is the capital of Italy?"))
                b2_t1_message2 = await turn21.add(Message(content="Rome is the capital of Italy.", role="assistant"))
    

    yield {
        "user": user,
        "branch": branch,
        "branch2": branch2,
        "b1_t1_message1": b1_t1_message1,
        "b1_t1_message2": b1_t1_message2,
        "b1_t2_message1": b1_t2_message1,
        "b1_t2_message2": b1_t2_message2,
        "b1_t3_message1": b1_t3_message1,
        "b1_t3_message2": b1_t3_message2,
        "b2_t1_message1": b2_t1_message1,
        "b2_t1_message2": b2_t1_message2,
    }




@pytest.mark.asyncio
async def test_branching(seeded_database):
    
    msgs = await Message.query().limit(20)
    assert len(msgs) == 6
    assert msgs[0].id == seeded_database['b1_t1_message1'].id
    assert msgs[1].id == seeded_database['b1_t1_message2'].id
    assert msgs[2].id == seeded_database['b1_t2_message1'].id
    assert msgs[3].id == seeded_database['b1_t2_message2'].id
    assert msgs[4].id == seeded_database['b1_t3_message1'].id
    assert msgs[5].id == seeded_database['b1_t3_message2'].id
    branch = await Branch.query().filter(lambda b: b.id == 2).last()
    with branch:
        msgs = await Message.query().limit(20)
        for m in msgs:
            print(m.role + ":", m.content)

    assert len(msgs) == 6
    assert msgs[0].id == seeded_database['b1_t1_message1'].id
    assert msgs[1].id == seeded_database['b1_t1_message2'].id
    assert msgs[2].id == seeded_database['b1_t2_message1'].id
    assert msgs[3].id == seeded_database['b1_t2_message2'].id
    assert msgs[4].id == seeded_database['b2_t1_message1'].id
    assert msgs[5].id == seeded_database['b2_t1_message2'].id




@pytest.mark.asyncio
async def test_post_query_with_comments_and_likes(seeded_database):
    # Test querying posts with comments
    posts = await Post.query().limit(10).join(Comment)
    assert len(posts) == 2
    assert len(posts[0].comments) == 3
    assert posts[0].comments[0].id == seeded_database['p1_comment1'].id
    assert posts[0].comments[1].id == seeded_database['p1_comment2'].id
    assert posts[0].comments[2].id == seeded_database['p1_comment3'].id
    assert len(posts[1].comments) == 2
    assert posts[1].comments[0].id == seeded_database['p2_comment1'].id
    assert posts[1].comments[1].id == seeded_database['p2_comment2'].id

    # Test querying posts with comments and likes
    posts = await Post.query().limit(10).join(Comment, Like)
    assert len(posts) == 2
    assert len(posts[0].comments) == 3
    assert len(posts[0].comments[0].likes) == 1
    assert len(posts[0].comments[1].likes) == 2
    assert len(posts[0].comments[2].likes) == 1
    assert len(posts[1].comments) == 2
    assert len(posts[1].comments[0].likes) == 4
    assert len(posts[1].comments[1].likes) == 1
