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
from promptview.utils.db_connections import PGConnectionManager


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

# @pytest_asyncio.fixture(scope="function", autouse=True)
# async def verify_clean_database():
#     await NamespaceManager.drop_all_namespaces()
#     await NamespaceManager.create_all_namespaces()


    
@pytest_asyncio.fixture(scope="function")
async def test_db_pool():
    """Create an isolated connection pool for each test."""
    # Close any existing pool
    if PGConnectionManager._pool is not None:
        await PGConnectionManager.close()
    
    # Create a unique pool for this test
    await PGConnectionManager.initialize(
        url=f"postgresql://ziggi:Aa123456@localhost:5432/promptview_test"
    )
    
    yield
    
    # Clean up this test's pool
    await PGConnectionManager.close()

@pytest_asyncio.fixture()
async def clean_database(test_db_pool):
    # Now uses an isolated pool
    await NamespaceManager.recreate_all_namespaces()
    yield
    await NamespaceManager.recreate_all_namespaces()



@pytest_asyncio.fixture()
async def seeded_database(clean_database):
    
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
    




@pytest.mark.asyncio
async def test_query_builders(seeded_database):
    user = seeded_database["user"]
    post1 = seeded_database["post1"]
    p1_like1 = seeded_database["p1_like1"]
    p1_like2 = seeded_database["p1_like2"]
    post2 = seeded_database["post2"]
    p2_like1 = seeded_database["p2_like1"]
    p2_like2 = seeded_database["p2_like2"]
    
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
    assert users[0].posts[0].id == post1.id
    assert users[0].posts[1].id == post2.id
    assert users[0].posts[0].likes[0].id == p1_like1.id
    assert users[0].posts[0].likes[1].id == p1_like2.id
    assert users[0].posts[1].likes[0].id == p2_like1.id
    assert users[0].posts[1].likes[1].id == p2_like2.id

    


@pytest_asyncio.fixture()
async def parametrized_database(clean_database, request):
    """
    Fixture that seeds the database with configurable number of users and related data.
    
    Parameters:
    - num_users: Number of users to create
    - posts_per_user: Number of posts each user will have
    - likes_per_post: Number of likes each post will have
    """
    num_users = request.param.get("num_users", 1)
    posts_per_user = request.param.get("posts_per_user", 2)
    likes_per_post = request.param.get("likes_per_post", 2)
    
    created_data = {
        "users": []
    }
    
    # Create users with posts and likes
    for u in range(num_users):
        user = await User(
            name=f"User {u}", 
            age=20 + u, 
            address=f"Address {u}"
        ).save()
        
        user_data = {"user": user, "posts": []}
        created_data["users"].append(user_data)
        
        # Create posts for this user
        for p in range(posts_per_user):
            post = await user.add(Post(
                title=f"Post {u}-{p}",
                content=f"Content for post {u}-{p}"
            ))
            
            post_data = {"post": post, "likes": []}
            user_data["posts"].append(post_data)
            
            # Create likes for this post
            for l in range(likes_per_post):
                like = await post.add(Like(post_id=post.id))
                post_data["likes"].append(like)
    
    yield created_data


# Define test scenarios with different data configurations
test_scenarios = [
    {"num_users": 1, "posts_per_user": 2, "likes_per_post": 2},
    {"num_users": 3, "posts_per_user": 2, "likes_per_post": 2},
    {"num_users": 1, "posts_per_user": 5, "likes_per_post": 3},
    {"num_users": 2, "posts_per_user": 3, "likes_per_post": 4},
]

# Create descriptive test IDs
def idfn(val):
    return f"{val['num_users']}u_{val['posts_per_user']}p_{val['likes_per_post']}l"

@pytest.mark.parametrize("parametrized_database", test_scenarios, indirect=True, ids=idfn)
@pytest.mark.asyncio
async def test_with_parametrized_data(parametrized_database):
    """Test queries with different database configurations."""
    data = parametrized_database
    expected_user_count = len(data["users"])
    
    # Test that we can query all users
    users_query = SelectQuerySet(User).select("*")
    users = await users_query.execute()
    assert len(users) == expected_user_count
    
    # Test full relationship query
    l_query = SelectQuerySet(Like).select("*")
    p_query = SelectQuerySet(Post).select("*").join(l_query)
    full_query = SelectQuerySet(User).select("*").join(p_query)
    
    full_results = await full_query.execute()
    assert len(full_results) == expected_user_count
    
    # Verify first user's data matches expected structure
    first_user_data = data["users"][0]
    first_user = full_results[0]
    expected_post_count = len(first_user_data["posts"])
    expected_like_count = len(first_user_data["posts"][0]["likes"])
    
    assert len(first_user.posts) == expected_post_count
    assert len(first_user.posts[0].likes) == expected_like_count
    
    # Verify user and post IDs match what was created
    for i, user_data in enumerate(data["users"]):
        user = full_results[i]
        assert user.id == user_data["user"].id
        
        for j, post_data in enumerate(user_data["posts"]):
            post = user.posts[j]
            assert post.id == post_data["post"].id
            
            for k, like in enumerate(post_data["likes"]):
                assert post.likes[k].id == like.id


