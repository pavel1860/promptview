import pytest
from datetime import datetime
from typing import AsyncGenerator, Generator, Any
from sqlalchemy import create_engine, text, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, Session
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from promptview.artifact_log.artifact_log2 import (
    Base,
    Head,
    Branch,
    Turn,
    TurnStatus,
    BaseArtifact,
    ArtifactLog,
    ArtifactQuery,
    create_artifact_table_for_model,
)
from promptview.model.model import Model
from promptview.model.fields import ModelField


# Test model for versioning
class TestModel(Model):
    name: str = ModelField(default="")
    value: int = ModelField(default=0)
    
    class Config:
        versioned = True
        database_type = "postgres"

# Initialize the namespace for TestModel

@pytest.fixture(scope="function")
def db_engine() -> Generator[Any, None, None]:
    """Create a test database engine."""
    # Connect to PostgreSQL server to create/drop test database
    postgres_url = "postgresql://snack:Aa123456@localhost:5432/postgres"
    test_db_name = "artifact_log_test"
    
    # Connect to default postgres database to create/drop test database
    conn = psycopg2.connect(postgres_url)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    # Drop test database if it exists and create it fresh
    cursor.execute(f"DROP DATABASE IF EXISTS {test_db_name}")
    cursor.execute(f"CREATE DATABASE {test_db_name}")
    
    cursor.close()
    conn.close()
    
    # Now connect to the test database
    DATABASE_URL = f"postgresql://snack:Aa123456@localhost:5432/{test_db_name}"
    engine = create_engine(DATABASE_URL)
    
    # Create ltree extension if it doesn't exist
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS ltree;"))
        conn.commit()
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    yield engine
    
    # Cleanup after tests
    Base.metadata.drop_all(engine)
    
    # Drop the test database
    conn = psycopg2.connect(postgres_url)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    cursor.execute(f"DROP DATABASE IF EXISTS {test_db_name}")
    cursor.close()
    conn.close()

@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create a new database session for a test."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    
    yield session
    
    session.close()

@pytest.fixture(scope="function")
async def artifact_log(db_session) -> AsyncGenerator[ArtifactLog, None]:
    """Create an ArtifactLog instance with initialized head."""
    log = ArtifactLog(db_session)
    await log.init_head()
    yield log

@pytest.mark.asyncio
async def test_init_head(artifact_log):
    """Test initializing a new head with main branch."""
    head = artifact_log.head
    assert head is not None
    assert head.branch.name == "main"
    assert str(head.branch.path) == "1"
    assert head.turn.index == 1
    assert head.turn.status == TurnStatus.STAGED

@pytest.mark.asyncio
async def test_stage_artifact(artifact_log, db_session):
    """Test staging a model instance as an artifact."""
    # Create a test model instance
    model = TestModel(name="test", value=42)
    await model.save()
    
    # Stage the model
    artifact = await artifact_log.stage_artifact(model)
    
    assert artifact is not None
    assert artifact.turn_id == artifact_log.head.turn.id
    assert artifact.model_id == model.id

@pytest.mark.asyncio
async def test_commit_turn(artifact_log):
    """Test committing a turn and creating a new one."""
    initial_turn = artifact_log.head.turn
    
    # Commit the turn
    new_turn = await artifact_log.commit_turn("Test commit")
    
    assert initial_turn.status == TurnStatus.COMMITTED
    assert initial_turn.ended_at is not None
    assert new_turn.index == initial_turn.index + 1
    assert new_turn.status == TurnStatus.STAGED
    assert artifact_log.head.turn == new_turn

@pytest.mark.asyncio
async def test_branch_creation(artifact_log):
    """Test creating a new branch from a turn."""
    # Create some history in main branch
    model = TestModel(name="test", value=42)
    await model.save()
    await artifact_log.stage_artifact(model)
    initial_turn = await artifact_log.commit_turn("Initial commit")
    
    # Create new branch
    new_branch = await artifact_log.branch_from(
        turn_id=initial_turn.id,
        name="feature",
        check_out=True
    )
    
    assert new_branch.name == "feature"
    assert str(new_branch.path).startswith(str(artifact_log.head.branch.path))
    assert artifact_log.head.branch == new_branch
    assert artifact_log.head.turn.index == 1

@pytest.mark.asyncio
async def test_artifact_query(artifact_log):
    """Test querying artifacts."""
    # Create some test data
    model1 = TestModel(name="test1", value=42)
    await model1.save()
    await artifact_log.stage_artifact(model1)
    turn1 = await artifact_log.commit_turn("First commit")
    
    model2 = TestModel(name="test2", value=84)
    await model2.save()
    await artifact_log.stage_artifact(model2)
    turn2 = await artifact_log.commit_turn("Second commit")
    
    # Query artifacts at different turns
    query = artifact_log.get_artifact(TestModel)
    
    # Test querying at specific turn
    results = await query.at_turn(turn1.id).execute()
    assert len(results) == 1
    assert isinstance(results[0], TestModel)
    assert results[0].name == "test1"
    
    # Test querying up to a turn
    results = await query.up_to_turn(turn2.id).execute()
    assert len(results) == 2
    assert {r.name for r in results} == {"test1", "test2"}

@pytest.mark.asyncio
async def test_revert_turn(artifact_log):
    """Test reverting the current turn."""
    # Create initial state
    model = TestModel(name="test", value=42)
    await model.save()
    await artifact_log.stage_artifact(model)
    initial_turn = artifact_log.head.turn
    
    # Revert the turn
    new_turn = await artifact_log.revert_turn()
    
    assert initial_turn.status == TurnStatus.REVERTED
    assert initial_turn.ended_at is not None
    assert new_turn.index == initial_turn.index + 1
    assert new_turn.status == TurnStatus.STAGED
    assert artifact_log.head.turn == new_turn

@pytest.mark.asyncio
async def test_revert_to_turn(artifact_log):
    """Test reverting to a specific turn."""
    # Create some history
    model1 = TestModel(name="test1", value=42)
    await model1.save()
    await artifact_log.stage_artifact(model1)
    turn1 = await artifact_log.commit_turn("First commit")
    
    model2 = TestModel(name="test2", value=84)
    await model2.save()
    await artifact_log.stage_artifact(model2)
    turn2 = await artifact_log.commit_turn("Second commit")
    
    # Revert to first turn
    new_turn = await artifact_log.revert_to_turn(turn1.id)
    
    # Check that turn2 is reverted
    turn2 = await artifact_log.get_turn(turn2.id)
    assert turn2.status == TurnStatus.REVERTED
    
    # Check that new turn is created correctly
    assert new_turn.index == turn1.index + 1
    assert new_turn.status == TurnStatus.STAGED
    assert artifact_log.head.turn == new_turn

@pytest.mark.asyncio
async def test_branched_versioning(artifact_log):
    """Test versioning with multiple branches."""
    # Create initial state in main branch
    model1 = TestModel(name="main1", value=42)
    await model1.save()
    await artifact_log.stage_artifact(model1)
    main_turn1 = await artifact_log.commit_turn("Main first commit")
    
    # Create feature branch
    feature_branch = await artifact_log.branch_from(
        turn_id=main_turn1.id,
        name="feature",
        check_out=True
    )
    
    # Add changes in feature branch
    model2 = TestModel(name="feature1", value=84)
    await model2.save()
    await artifact_log.stage_artifact(model2)
    feature_turn1 = await artifact_log.commit_turn("Feature first commit")
    
    # Switch back to main branch
    await artifact_log.checkout_branch(main_turn1.branch.id)
    
    # Add different changes in main branch
    model3 = TestModel(name="main2", value=126)
    await model3.save()
    await artifact_log.stage_artifact(model3)
    main_turn2 = await artifact_log.commit_turn("Main second commit")
    
    # Query main branch
    main_results = await artifact_log.get_artifact(TestModel).execute()
    assert len(main_results) == 2
    assert isinstance(main_results[0], TestModel)
    assert {r.name for r in main_results} == {"main1", "main2"}
    
    # Query feature branch
    await artifact_log.checkout_branch(feature_branch.id)
    feature_results = await artifact_log.get_artifact(TestModel).execute()
    assert len(feature_results) == 2
    assert isinstance(feature_results[0], TestModel)
    assert {r.name for r in feature_results} == {"main1", "feature1"} 