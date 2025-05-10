import pytest
import pytest_asyncio

import datetime as dt
from typing import List
from promptview.model2 import Model, ModelField, KeyField, RelationField
from promptview.model2 import NamespaceManager
from promptview.model2 import Turn as BaseTurn, TurnModel, Branch
from __tests__.utils import clean_database, test_db_pool
from promptview.model2.version_control_models import VersioningError

class Like(TurnModel):
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    post_id: int = ModelField(foreign_key=True)  
    user_id: int = ModelField(foreign_key=True)

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
    likes: List[Like] = RelationField(foreign_key="user_id")




class Turn(BaseTurn):
    posts: List[Post] = RelationField(foreign_key="turn_id")
    likes: List[Like] = RelationField(foreign_key="turn_id")




@pytest.mark.asyncio
async def test_turn_model_error_when_no_turn_id_is_provided(clean_database):
    user = await User(name="Test", age=30, address="Test").save()
    with pytest.raises(VersioningError):
        await Post(title="Test", content="Test", user_id=user.id).save()
    with pytest.raises(VersioningError):
        await user.add(Post(title="Test", content="Test"))



@pytest.mark.asyncio
async def test_missing_foreign_key_context(clean_database):
    branch = await Branch.query().where(id=1).first()
    user = await User(name="Arnold", age=30, address="test").save()
    with pytest.raises(ValueError):
        with branch:    
            async with Turn.start():
                post = await user.add(Post(title="post 1", content="content 1"))
                like1 = await post.add(Like(post_id=post.id))
                like2 = await post.add(Like(post_id=post.id))



@pytest.mark.asyncio
async def test_turn_revert(clean_database):
    branch = await Branch.query().where(id=1).first()
    user = await User(name="Arnold", age=30, address="test").save()
    
    with branch:    
        with user:
            async with Turn.start():
                post1 = await user.add(Post(title="post 1", content="content 1"))
                like1 = await post1.add(Like(post_id=post1.id))
                like2 = await post1.add(Like(post_id=post1.id))

        try:
            async with Turn.start():
                post2 = await user.add(Post(title="post 2", content="content 2"))
                like3 = await post2.add(Like(post_id=post2.id))
                like4 = await post2.add(Like(post_id=post2.id))
        except Exception as e:
            pass
        
        user = await user.query().join(Post.query().join(Like)).first()
        assert len(user.posts) == 1
        assert len(user.posts[0].likes) == 2

            

                
                
