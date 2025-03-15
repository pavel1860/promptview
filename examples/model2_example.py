import sys
sys.path.append("..")
import sys
import os

# Add the parent directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from promptview.model2.model import Model
from promptview.model2.fields import ModelField, KeyField
import asyncio


class User(Model):
    # Set namespace name and database type
    _namespace_name = "users"
    _db_type = "postgres"
    
    # Fields
    id: int = KeyField(primary_key=True)
    name: str = ModelField()
    age: int = ModelField()


class Post(Model):
    # Set namespace name and database type
    _namespace_name = "posts"
    _db_type = "postgres"
    
    # Fields
    id: int = KeyField(primary_key=True)
    title: str = ModelField()
    content: str = ModelField()
    author_id: int = ModelField()


async def main():
    # Initialize the models (create tables)
    print("Creating tables...")
    await User.initialize()
    await Post.initialize()
    
    # Create a user
    print("Creating user...")
    user = User(name="John Doe", age=30)
    await user.save()
    print(f"User created with ID: {user.id}")
    
    # Create a post
    print("Creating post...")
    post = Post(title="Hello World", content="This is my first post", author_id=user.id)
    await post.save()
    print(f"Post created with ID: {post.id}")
    
    # Get the user by ID
    print("Getting user...")
    retrieved_user = await User.get(user.id)
    print(f"Retrieved user: {retrieved_user}")
    
    # Query users
    print("Querying users...")
    users = await User.query().filter(name="John Doe").execute()
    print(f"Found users: {users}")


if __name__ == "__main__":
    asyncio.run(main())