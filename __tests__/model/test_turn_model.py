import os
os.environ["POSTGRES_URL"] = "postgresql://ziggi:Aa123456@localhost:5432/promptview_test"

import pytest
import pytest_asyncio
from promptview.model2 import Model, ArtifactModel, ModelField, RelationField, ArtifactModel
from promptview.model2.fields import KeyField, RelationField, ModelField
from promptview.prompt import Block, ToolCall



from enum import StrEnum
from typing import TYPE_CHECKING, Any, List, Literal, Type
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
async def seeded_message_database(clean_database):
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

@pytest_asyncio.fixture()
async def seeded_post_database(clean_database):
    
    
    
        await NamespaceManager.create_all_namespaces()

        data = {}
        
        user = await User(name="John", age=30).save()
        branch = await Branch.get(1)
        
        with user:
            with branch:                
                async with Turn.start():
                    post1 = await Post(title="Post 1 Title", content="Post 1 Content").save()
                
                async with Turn.start():
                    p1_comment1 = await post1.add(Comment(content="post 1 comment 1"))
                    p1c1_like1 = await p1_comment1.add(Like(type=LikeType.LIKE, ))
                    p1_comment2 = await post1.add(Comment(content="post 1 comment 2"))
                
                async with Turn.start():
                    p1c2_like1 = await p1_comment2.add(Like(type=LikeType.LIKE, ))
                    p1c2_like2 = await p1_comment2.add(Like(type=LikeType.DISLIKE, ))
                    p1_comment3 = await post1.add(Comment(content="post 1 comment 3"))
                async with Turn.start():
                    p1c3_like1 = await p1_comment3.add(Like(type=LikeType.LIKE, ))

                async with Turn.start():
                    post2 = await Post(title="Post 2 Title", content="Post 2 Content").save()
                    p2_comment1 = await post2.add(Comment(content="post 2 comment 1"))
                    p2c1_like1 = await p2_comment1.add(Like(type=LikeType.LIKE, ))
                    p2c1_like2 = await p2_comment1.add(Like(type=LikeType.DISLIKE, ))
                
                async with Turn.start():
                    p2c1_like3 = await p2_comment1.add(Like(type=LikeType.LIKE, ))
                    p2c1_like4 = await p2_comment1.add(Like(type=LikeType.DISLIKE, ))
                    p2_comment2 = await post2.add(Comment(content="post 2 comment 2"))
                async with Turn.start():
                    p2c2_like1 = await p2_comment2.add(Like(type=LikeType.LIKE, ))

        yield {
            "user": user,
            "post1": post1,
            "p1_comment1": p1_comment1,
            "p1c1_like1": p1c1_like1,
            "p1_comment2": p1_comment2,
            "p1c2_like1": p1c2_like1,
            "p1c2_like2": p1c2_like2,
            "p1_comment3": p1_comment3,
            "p1c3_like1": p1c3_like1,
            "post2": post2,
            "p2_comment1": p2_comment1,
            "p2c1_like1": p2c1_like1,
            "p2c1_like2": p2c1_like2,
            "p2c1_like3": p2c1_like3,
            "p2c1_like4": p2c1_like4,
            "p2_comment2": p2_comment2,
            "p2c2_like1": p2c2_like1,
        }



@pytest.mark.asyncio
async def test_branching(seeded_message_database):
    data = seeded_message_database
    
    msgs = await Message.query().limit(20)
    assert len(msgs) == 6
    assert msgs[0].id == data['b1_t1_message1'].id
    assert msgs[1].id == data['b1_t1_message2'].id
    assert msgs[2].id == data['b1_t2_message1'].id
    assert msgs[3].id == data['b1_t2_message2'].id
    assert msgs[4].id == data['b1_t3_message1'].id
    assert msgs[5].id == data['b1_t3_message2'].id
    branch = await Branch.query().filter(lambda b: b.id == 2).last()
    with branch:
        msgs = await Message.query().limit(20)
        for m in msgs:
            print(m.role + ":", m.content)

    assert len(msgs) == 6
    assert msgs[0].id == data['b1_t1_message1'].id
    assert msgs[1].id == data['b1_t1_message2'].id
    assert msgs[2].id == data['b1_t2_message1'].id
    assert msgs[3].id == data['b1_t2_message2'].id
    assert msgs[4].id == data['b2_t1_message1'].id
    assert msgs[5].id == data['b2_t1_message2'].id




@pytest.mark.asyncio
async def test_post_query_with_comments_and_likes(seeded_post_database):
    # Test querying posts with comments
    data = seeded_post_database
    posts = await Post.query().limit(10).order_by("created_at").join(Comment)
    assert len(posts) == 2
    assert len(posts[0].comments) == 3
    assert posts[0].comments[0].id == data['p1_comment1'].id
    assert posts[0].comments[1].id == data['p1_comment2'].id
    assert posts[0].comments[2].id == data['p1_comment3'].id
    assert len(posts[1].comments) == 2
    assert posts[1].comments[0].id == data['p2_comment1'].id
    assert posts[1].comments[1].id == data['p2_comment2'].id

    # Test querying posts with comments and likes
    posts = await Post.query().limit(10).order_by("created_at").join(Comment.query().join(Like))
    assert len(posts) == 2
    assert len(posts[0].comments) == 3
    assert len(posts[0].comments[0].likes) == 1
    assert len(posts[0].comments[1].likes) == 2
    assert len(posts[0].comments[2].likes) == 1
    assert len(posts[1].comments) == 2
    assert len(posts[1].comments[0].likes) == 4
    assert len(posts[1].comments[1].likes) == 1
