import pytest
from typing import List, Literal

import pytest_asyncio

from promptview.model3.fields import ModelField, KeyField, RelationField
from promptview.model3.model3 import Model
from promptview.model3.namespace_manager2 import NamespaceManager
from promptview.model3.relation_model import RelationModel
from promptview.model3.postgres2.pg_query_set import select


# -------------------------
# Models
# -------------------------

class Message(Model):
    id: int = KeyField(primary_key=True)
    content: str = ModelField()
    role: Literal["user", "assistant"] = ModelField()
    turn_id: int = ModelField(foreign_key=True)
    turn: "Turn | None" = RelationField(
        foreign_key="id",
        primary_key="turn_id",
    )


class Turn(Model):
    id: int = KeyField(primary_key=True)
    index: int | None = ModelField(default=None)
    user_id: int = ModelField(foreign_key=True)
    conv_id: int = ModelField(foreign_key=True)
    messages: List[Message] = RelationField(
        foreign_key="turn_id",
    )


class Participant(RelationModel):
    id: int = KeyField(primary_key=True)
    user_id: int = ModelField(foreign_key=True)
    conv_id: int = ModelField(foreign_key=True)


class Conversation(Model):
    id: int = KeyField(primary_key=True)
    title: str = ModelField()
    user: List["User"] = RelationField(
        primary_key="id",
        foreign_key="id",
        junction_keys=["conv_id", "user_id"],
        junction_model=Participant
    )
    turns: List[Turn] = RelationField(
        foreign_key="conv_id",
    )


class User(Model):
    id: int = KeyField(primary_key=True)
    name: str = ModelField()
    conversations: List[Conversation] = RelationField(
        primary_key="id",
        foreign_key="id",
        junction_keys=["user_id", "conv_id"],
        junction_model=Participant
    )

@pytest_asyncio.fixture()
async def setup_db():
    """Ensure we start with a clean DB schema for the tests."""
    # Drop all namespaces (tables)
    NamespaceManager.drop_all_tables()
    await NamespaceManager.initialize_all()
    yield
    # Drop again after tests
    NamespaceManager.drop_all_tables()
# -------------------------
# Test
# -------------------------

@pytest.mark.asyncio
async def test_conversation_relations(setup_db):

    # Create user & conversation
    user1 = await User(name="jon").save()
    conv1 = await Conversation(title="jon's conv").save()
    await Participant(user_id=user1.id, conv_id=conv1.id).save()

    # First turn with messages
    turn11 = await Turn(index=1, user_id=user1.id, conv_id=conv1.id).save()
    await Message(content="hello", role="user", turn_id=turn11.id).save()
    await Message(content="world", role="assistant", turn_id=turn11.id).save()

    # Second turn with messages
    turn12 = await Turn(index=2, user_id=user1.id, conv_id=conv1.id).save()
    await Message(content="who are you?", role="user", turn_id=turn12.id).save()
    await Message(content="I'm an Agent", role="assistant", turn_id=turn12.id).save()

    # -------------------------
    # 1) Conversation -> Turn -> Message
    # -------------------------
    convs = await select(Conversation).include(
        select(Turn).include(Message)
    ).execute()

    assert len(convs) == 1
    assert len(convs[0].turns) == 2
    assert len(convs[0].turns[0].messages) == 2
    assert len(convs[0].turns[1].messages) == 2

    # -------------------------
    # 2) User -> Conversation -> Turn (no messages)
    # -------------------------
    users = await select(User).include(
        select(Conversation).include(Turn)
    ).execute()

    assert len(users) == 1
    assert len(users[0].conversations) == 1
    assert len(users[0].conversations[0].turns) == 2
    assert len(users[0].conversations[0].turns[0].messages) == 0
    assert len(users[0].conversations[0].turns[1].messages) == 0

    # -------------------------
    # 3) User -> Conversation -> Turn -> Message
    # -------------------------
    users = await select(User).include(
        select(Conversation).include(
            select(Turn).include(Message)
        )
    ).execute()

    assert len(users) == 1
    assert len(users[0].conversations) == 1
    assert len(users[0].conversations[0].turns) == 2
    assert len(users[0].conversations[0].turns[0].messages) == 2
    assert len(users[0].conversations[0].turns[1].messages) == 2
