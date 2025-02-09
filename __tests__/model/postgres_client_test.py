import pytest
import pytest_asyncio
import datetime as dt
from promptview.model.fields import ModelField, IndexType
from promptview.model.model import Model
from promptview.model.resource_manager import connection_manager
from promptview.model.vectors.openai_vectorizer import OpenAISmallVectorizer
from promptview.model.postgres_client import PostgresClient

class BasicPostgresModel(Model):
    created_at: dt.datetime = ModelField(auto_now_add=True)
    updated_at: dt.datetime = ModelField(auto_now=True)
    topic: str = ModelField(index=IndexType.Text, vec="dense")
    content: str = ModelField(vec=["dense"])
    uuid: str = ModelField(index=IndexType.Uuid)
    order: int = ModelField(index=IndexType.Integer)
    
    class VectorSpace:
        dense: OpenAISmallVectorizer

@pytest_asyncio.fixture()
async def postgres_client():
    client = PostgresClient(
        database="test_db",
        user="postgres",
        password="postgres",
        host="localhost",
        port=5432
    )
    await client.connect()
    yield client
    await client.close()

@pytest_asyncio.fixture()
async def seeded_database(postgres_client):
    # Create test collection/table
    vector_spaces = [
        connection_manager._namespaces["BasicPostgresModel"].vector_spaces["dense"]
    ]
    await postgres_client.create_collection(
        "BasicPostgresModel",
        vector_spaces=vector_spaces,
        indices=[
            {"field": "topic", "schema": "text"},
            {"field": "uuid", "schema": "text"},
            {"field": "order", "schema": "integer"}
        ]
    )

    # Insert test data
    test_data = [
        {
            "created_at": dt.datetime(2018, 1, 1),
            "topic": "animals",
            "content": "turtles are slow",
            "uuid": "1234",
            "order": 1
        },
        {
            "created_at": dt.datetime(2019, 1, 1),
            "topic": "animals",
            "content": "dolphins are cool",
            "uuid": "1432",
            "order": 2,
        },
        {
            "created_at": dt.datetime(2021, 1, 1),
            "topic": "physics",
            "content": "quantum mechanics is weird",
            "uuid": "1154",
            "order": 3,
        },
        {
            "created_at": dt.datetime(2022, 1, 1),
            "topic": "physics",
            "content": "energy is mass and mass is energy",
            "uuid": "6467",
            "order": 4,
        },
        {
            "created_at": dt.datetime(2023, 1, 1),
            "topic": "movies",
            "content": "the matrix movie came out in 2000",
            "uuid": "1934",
            "order": 5,
        },
        {
            "created_at": dt.datetime(2024, 1, 1),
            "topic": "movies",
            "content": "friends is the worst show",
            "uuid": "1934",
            "order": 6,
        }
    ]

    # Generate vectors for test data
    vectors = {}
    vectorizer = vector_spaces[0].vectorizer
    for item in test_data:
        if "dense" not in vectors:
            vectors["dense"] = []
        vectors["dense"].append(await vectorizer.encode(item["content"]))

    await postgres_client.upsert(
        namespace="BasicPostgresModel",
        vectors=vectors,
        metadata=test_data
    )

    yield postgres_client

    # Cleanup
    await postgres_client.delete_collection("BasicPostgresModel")

@pytest.mark.asyncio
async def test_basic_search(seeded_database):
    # Test vector search with cosine similarity
    vectorizer = connection_manager._namespaces["BasicPostgresModel"].vector_spaces["dense"].vectorizer
    
    # Search for animal-related content
    query_vec = await vectorizer.encode("I like cats")
    results = await seeded_database.search(
        collection_name="BasicPostgresModel",
        query={"dense": query_vec},
        limit=2
    )
    assert len(results) == 2
    for rec in results:
        assert rec["payload"]["topic"] == "animals"

    # Search for physics-related content
    query_vec = await vectorizer.encode("I want to study quantum energy physics")
    results = await seeded_database.search(
        collection_name="BasicPostgresModel",
        query={"dense": query_vec},
        limit=2
    )
    assert len(results) == 2
    for rec in results:
        assert rec["payload"]["topic"] == "physics"

@pytest.mark.asyncio
async def test_filtering(seeded_database):
    # Test filtering with different conditions
    results = await seeded_database.scroll(
        collection_name="BasicPostgresModel",
        filters=lambda x: x.topic == "animals"
    )
    records, _ = results
    assert len(records) == 2
    for rec in records:
        assert rec["payload"]["topic"] == "animals"

    # Test OR condition
    results = await seeded_database.scroll(
        collection_name="BasicPostgresModel",
        filters=lambda x: (x.topic == "animals") | (x.topic == "physics")
    )
    records, _ = results
    assert len(records) == 4
    for rec in records:
        assert rec["payload"]["topic"] in ["animals", "physics"]

@pytest.mark.asyncio
async def test_temporal_query(seeded_database):
    # Test date range queries
    results = await seeded_database.scroll(
        collection_name="BasicPostgresModel",
        filters=lambda x: x.created_at > dt.datetime(2021, 1, 1)
    )
    records, _ = results
    assert len(records) == 3
    for rec in records:
        assert rec["payload"]["created_at"] > dt.datetime(2021, 1, 1).isoformat()

    # Test date range with multiple conditions
    results = await seeded_database.scroll(
        collection_name="BasicPostgresModel",
        filters=lambda x: (x.created_at >= dt.datetime(2021, 1, 1)) & (x.created_at < dt.datetime(2024, 1, 1))
    )
    records, _ = results
    assert len(records) == 3
    for rec in records:
        created_at = dt.datetime.fromisoformat(rec["payload"]["created_at"])
        assert dt.datetime(2021, 1, 1) <= created_at < dt.datetime(2024, 1, 1)

@pytest.mark.asyncio
async def test_ordering(seeded_database):
    # Test ordering by different fields
    results = await seeded_database.scroll(
        collection_name="BasicPostgresModel",
        order_by={"key": "order", "direction": "asc"}
    )
    records, _ = results
    orders = [r["payload"]["order"] for r in records]
    assert orders == [1, 2, 3, 4, 5, 6]

    results = await seeded_database.scroll(
        collection_name="BasicPostgresModel",
        order_by={"key": "order", "direction": "desc"}
    )
    records, _ = results
    orders = [r["payload"]["order"] for r in records]
    assert orders == [6, 5, 4, 3, 2, 1]

@pytest.mark.asyncio
async def test_pagination(seeded_database):
    # Test pagination with limit and offset
    results, next_offset = await seeded_database.scroll(
        collection_name="BasicPostgresModel",
        limit=2,
        offset=0
    )
    assert len(results) == 2
    assert next_offset == 2

    results, next_offset = await seeded_database.scroll(
        collection_name="BasicPostgresModel",
        limit=2,
        offset=next_offset
    )
    assert len(results) == 2
    assert next_offset == 4

    results, next_offset = await seeded_database.scroll(
        collection_name="BasicPostgresModel",
        limit=2,
        offset=next_offset
    )
    assert len(results) == 2
    assert next_offset == 6

    results, next_offset = await seeded_database.scroll(
        collection_name="BasicPostgresModel",
        limit=2,
        offset=next_offset
    )
    assert len(results) == 0
    assert next_offset is None 