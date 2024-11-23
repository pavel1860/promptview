import pytest
import pytest_asyncio
import datetime as dt
from promptview.model.fields import ModelField, IndexType
from promptview.model.model import Model
from promptview.model.resource_manager import connection_manager
from promptview.model.vectors.bm25_vectorizer import BM25Vectorizer
from promptview.model.vectors.openai_vectorizer import OpenAISmallVectorizer, OpenAILargeVectorizer

class BasicModel(Model):
    created_at: dt.datetime = ModelField(auto_now_add=True)
    updated_at: dt.datetime = ModelField(auto_now=True)
    topic: str = ModelField(index=IndexType.Text, vec="dense")
    content: str = ModelField(vec=["dense", "sparse"])
    uuid: str = ModelField(index=IndexType.Uuid)
    
    class VectorSpace:
        dense: OpenAISmallVectorizer
        sparse: BM25Vectorizer



# @pytest.fixture(scope="function")
# @pytest_asyncio.fixture(scope="session")
@pytest_asyncio.fixture()
async def seeded_database():
    points = [
        BasicModel(
            topic="animals",
            content="I like turtles",
            uuid="1234"
        ),
        BasicModel(
            topic="animals",
            content="dolphins are cool",
            uuid="1432"
        ),
        BasicModel(
            topic="physics",
            content="quantum mechanics is weird",
            uuid="1154"
        ),
        BasicModel(
            topic="physics",
            content="energy is mass and mass is energy",
            uuid="6467"
        ),
        BasicModel(
            topic="movies",
            content="I like the matrix",
            uuid="1934"
        ),
        BasicModel(
            topic="movies",
            content="friends is the worst show",
            uuid="1934"
        )
    ]
    await BasicModel.batch_upsert(points)
    conn = connection_manager._qdrant_connection

    yield conn
    
    await conn.delete_collection("BasicModel")
    connection_manager._namespaces = {}
    connection_manager._active_namespaces = {}


@pytest.mark.asyncio
async def test_query(seeded_database):
    # conn = anext(seeded_database)
    print(seeded_database)
    # collections = await conn.get_collections()
    recs = await BasicModel.similar("I like cats").limit(2)
    assert len(recs) == 2
    for rec in recs:
        assert rec.topic == "animals"
    
    recs = await BasicModel.similar("I want to study physics").limit(2)
    assert len(recs) == 2
    for rec in recs:
        assert rec.topic == "physics"
        
    recs = await BasicModel.similar("what movie should I watch").limit(2)
    assert len(recs) == 2
    for rec in recs:
        assert rec.topic == "movies"
        
        
@pytest.mark.asyncio
async def test_named_query(seeded_database):
    recs = await BasicModel.similar("I like cats", vec="dense").limit(2)
    assert len(recs) == 2
    for rec in recs:
        assert rec.topic == "animals"
    
    recs = await BasicModel.similar("I want to study physics", vec="dense").limit(2)
    assert len(recs) == 2
    for rec in recs:
        assert rec.topic == "physics"
        
    recs = await BasicModel.similar("what movie should I watch", vec="dense").limit(2)
    assert len(recs) == 2
    for rec in recs:
        assert rec.topic == "movies"
        
        
        
        
@pytest.mark.asyncio        
async def test_filtering(seeded_database):
    recs = await BasicModel.similar("the matrix is a great movie").filter(lambda x: x.topic == "animals")
    for rec in recs:
        assert rec.topic == "animals"
        
    recs = await BasicModel.similar("the matrix is a great movie").filter(lambda x: x.topic == "movies")
    for rec in recs:
        assert rec.topic == "movies"
        
    recs = await BasicModel.similar("the matrix is a great movie").filter(lambda x: (x.topic == "animals") | (x.topic == "physics"))
    for rec in recs:
        assert rec.topic in ["animals", "physics"]