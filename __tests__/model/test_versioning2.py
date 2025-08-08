# %%
# Set the file name (required)

__file__ = "testing.ipynb"
# Add ipython magics
import ipytest
import pytest


ipytest.autoconfig(run_in_thread=True)


# %% 
%%ipytest
import pytest
import asyncio
from promptview.model3.fields import KeyField, ModelField
from promptview.model3.versioning.models import Branch, Turn, TurnStatus, VersionedModel
from promptview.model3.versioning.graph import VersionGraph
from promptview.model3.versioning.backends.postgres import PostgresBranchManager, PostgresTurnManager
from promptview.model3.namespace_manager2 import NamespaceManager
import pytest_asyncio


@pytest_asyncio.fixture()
async def setup_db():
    """Ensure we start with a clean DB schema for the tests."""
    # Drop all namespaces (tables)
    NamespaceManager.drop_all_tables()
    yield
    # Drop again after tests
    NamespaceManager.drop_all_tables()
    
class Message(VersionedModel):
    id: int = KeyField(primary_key=True)
    text: str = ModelField()
    author: str = ModelField()

# %%
%%ipytest


def test_sorted():
    print("test_sorted")
    assert sorted([4, 2, 1, 3]) == [1, 2, 3, 4]
    

# %%
%%ipytest


@pytest.mark.asyncio
async def test_version_graph_flow(setup_db):
    await NamespaceManager.initialize_all()

    pg_branch_mgr = PostgresBranchManager()
    pg_turn_mgr = PostgresTurnManager()
    graph = VersionGraph(pg_branch_mgr, pg_turn_mgr)

    # Create root branch
    root_branch = await Branch(name="main").save()

    # Add messages in main branch
    async with graph.branch_context(root_branch):
        async with graph.start_turn():
            m1 = await Message(text="Hello world!", author="Alice").save()
            m2 = await Message(text="How are you?", author="Alice").save()

        async with graph.start_turn():
            m3 = await Message(text="I am fine.", author="Bob").save()

    # Verify all messages got correct branch/turn IDs
    msgs_main = await Message.query(branch=root_branch.id).all()
    assert all(m.branch_id == root_branch.id for m in msgs_main)
    assert all(m.turn_id is not None for m in msgs_main)

    # Fork from latest turn in main
    latest_turn = await graph.latest_turn(root_branch.id)
    new_branch = await graph.fork_from(latest_turn, name="experiment")

    # Add message in fork
    async with graph.branch_context(new_branch):
        async with graph.start_turn():
            m4 = await Message(text="This is a forked branch", author="Charlie").save()

    # Diff between branches
    only_main, only_experiment = await graph.diff_turns(root_branch.id, new_branch.id)
    assert len(only_main) > 0
    assert len(only_experiment) > 0

    # Test revert on error
    with pytest.raises(ValueError):
        async with graph.branch_context(root_branch):
            async with graph.start_turn():
                await Message(text="This will fail", author="X").save()
                raise ValueError("Simulated failure")

    reverted_turns = await Turn.query(branch=root_branch.id, status=TurnStatus.REVERTED).all()
    assert any(t.message == "ValueError: Simulated failure" for t in reverted_turns)

# %%
import pytest
import asyncio
from promptview.model3.fields import KeyField, ModelField
from promptview.model3.versioning.models import Branch, Turn, TurnStatus, VersionedModel
from promptview.model3.versioning.graph import VersionGraph
from promptview.model3.versioning.backends.postgres import PostgresBranchManager, PostgresTurnManager
from promptview.model3.postgres2.pg_query_set import select
from promptview.model3.namespace_manager2 import NamespaceManager
import pytest_asyncio

class Message(VersionedModel):
    id: int = KeyField(primary_key=True)
    text: str = ModelField()
    author: str = ModelField()
await NamespaceManager.initialize_all()

# %%

graph = VersionGraph()


root_branch = await Branch(name="main").save()


# %%


async with graph.branch_context(root_branch):
    async with graph.start_turn():
        m1 = await Message(text="Hello world!", author="Alice").save()
        m2 = await Message(text="How are you?", author="Alice").save()

    async with graph.start_turn():
        m3 = await Message(text="I am fine.", author="Bob").save()

# %%

latest_turn = await graph.latest_turn(root_branch.id)
new_branch = await graph.fork_from(latest_turn, name="experiment")

async with graph.branch_context(new_branch):
    async with graph.start_turn():
        m4 = await Message(text="This is a forked branch", author="Charlie").save()



# %%
await select(Branch).use_cte(Branch.recursive_cte(1)).print()
# select(Message).query.columns
# %%

branch = await Branch.get(1)
branch
with branch:
    turns = await select(Turn).where(status=TurnStatus.COMMITTED).print()


turns


# %%








# with CteRepo(Branch, Turn) as repo:
with Branch.cte() as b:
    with Turn.cte().limit(1) as t:
        Message.query(cte=[b, t]).print()
    

