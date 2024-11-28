import pytest_asyncio
import pytest
from promptview.model.model import Model, Field
from promptview.model.fields import ModelField, IndexType
from promptview.model.vectors.openai_vectorizer import OpenAISmallVectorizer, OpenAILargeVectorizer
from promptview.model.resource_manager import connection_manager
import datetime as dt





@pytest.mark.asyncio
async def test_single_space_basic():
    try:
        conn = connection_manager._qdrant_connection
        class BasicModel(Model):
            created_at: dt.datetime = ModelField(auto_now_add=True)
            updated_at: dt.datetime = ModelField(auto_now=True)
            name: str = ModelField(index=IndexType.Text)
            content: str = ModelField()
            uuid: str = ModelField(index=IndexType.Uuid)
            
            class VectorSpace:
                dense: OpenAISmallVectorizer            
        
        model = BasicModel(
            name="test",
            content="this is a test",
            uuid="1234"
        )
        assert model.created_at is not None
        assert model.updated_at is not None
        assert model.id is not None
        
        assert len(connection_manager._namespaces) == 1
        assert len(connection_manager._active_namespaces) == 0
        
        col_res = await conn.get_collections()
        assert len(col_res.collections) == 0
        
        await model.save()
        
        assert len(connection_manager._namespaces) == 1
        assert len(connection_manager._active_namespaces) == 1
    finally:
        await conn.delete_collection("BasicModel")
        connection_manager._namespaces = {}
        connection_manager._active_namespaces = {}
    
    
    
@pytest.mark.asyncio
async def test_quering_single_model():
    
    try:
        conn = connection_manager._qdrant_connection
        class BasicModel(Model):
            created_at: dt.datetime = ModelField(auto_now_add=True)
            updated_at: dt.datetime = ModelField(auto_now=True)
            topic: str = ModelField(index=IndexType.Text)
            content: str = ModelField()
            uuid: str = ModelField(index=IndexType.Uuid)
            
            class VectorSpace:
                dense: OpenAISmallVectorizer 

        
        await BasicModel(
            topic="animals",
            content="I like turtles",
            uuid="1234"
        ).save()     


        await BasicModel(
            topic="physics",
            content="energy is mass and mass is energy",
            uuid="6467"
        ).save()   
        
        
        msg = await BasicModel.similar("I like cats").first()
        assert msg is not None
        assert msg.content == "I like turtles"
        msg = await BasicModel.similar("quantom").first()
        assert msg.content == "energy is mass and mass is energy"    

    finally:
        await conn.delete_collection("BasicModel")
        connection_manager._namespaces = {}
        connection_manager._active_namespaces = {}






@pytest.mark.asyncio
async def test_filtering_single_model():
    
    try:
        conn = connection_manager._qdrant_connection
        class BasicModel(Model):
            created_at: dt.datetime = ModelField(auto_now_add=True)
            updated_at: dt.datetime = ModelField(auto_now=True)
            topic: str = ModelField(index=IndexType.Text)
            content: str = ModelField()
            uuid: str = ModelField(index=IndexType.Uuid)
            
            class VectorSpace:
                dense: OpenAISmallVectorizer 

        
        await BasicModel(
            topic="animals",
            content="I like turtles",
            uuid="1234"
        ).save()       

        await BasicModel(
            topic="animals",
            content="dolphins are cool",
            uuid="1432"
        ).save()       

        await BasicModel(
            topic="physics",
            content="quantum mechanics is weird",
            uuid="1154"
        ).save()       

        await BasicModel(
            topic="physics",
            content="energy is mass and mass is energy",
            uuid="6467"
        ).save()       

        await BasicModel(
            topic="movies",
            content="I like the matrix",
            uuid="1934"
        ).save()


        await BasicModel(
            topic="movies",
            content="friends is the worst show",
            uuid="1934"
        ).save()
        
        msgs = await BasicModel.filter(lambda x: (x.topic == "animals"))
        for m in msgs:
            assert m.topic == "animals"
        msgs = await BasicModel.filter(lambda x: (x.topic == "movies"))
        for m in msgs:
            assert m.topic == "movies"        
        msgs = await BasicModel.filter(lambda x: (x.topic == "animals") | (x.topic == "physics"))
        for m in msgs:
            assert m.topic in ["animals", "physics"]
            
        msgs = await BasicModel.filter(lambda x: (x.topic == "movies") | (x.topic == "physics"))
        for m in msgs:
            assert m.topic in ["movies", "physics"]
        
    finally:
        await conn.delete_collection("BasicModel")
        connection_manager._namespaces = {}
        connection_manager._active_namespaces = {}



class BasicModel(Model):
    created_at: dt.datetime = ModelField(auto_now_add=True)
    updated_at: dt.datetime = ModelField(auto_now=True)
    topic: str = ModelField(index=IndexType.Text)
    content: str = ModelField()
    uuid: str = ModelField(index=IndexType.Uuid)
    
    class VectorSpace:
        dense: OpenAISmallVectorizer 



@pytest_asyncio.fixture()
async def simple_seeded_database():
    conn = connection_manager._qdrant_connection
    try:
        _ = await conn.get_collection("BasicModel")
        await conn.delete_collection("BasicModel")
    except Exception as e:
        pass
    
    msg1 = await BasicModel(
                topic="animals",
                content="I like turtles",
                uuid="1234"
        ).save()

    msg2 = await BasicModel(
            topic="movies",
            content="the matrix movie came out in 2000",
            uuid="1432"
        ).save()
    yield {
            "connection_manager": connection_manager,
            "messages": [msg1, msg2]
        }
    await conn.delete_collection("BasicModel")
    connection_manager._namespaces = {}
    connection_manager._active_namespaces = {}

@pytest.mark.asyncio
async def test_id_retrieval(simple_seeded_database):
    
    [msg1, msg2] = simple_seeded_database["messages"]  
    
    res_empty = await BasicModel.get("60759263-2849-1234-93af-5ac2e8c87f5c")
    assert res_empty is None
    
    res1 = await BasicModel.get(msg1.id)
    assert res1 is not None
    assert res1.id == msg1.id
    assert res1.topic == msg1.topic
    assert res1.content == msg1.content
    
    res2 = await BasicModel.get(msg2.id)
    assert res2 is not None
    assert res2.id == msg2.id
    assert res2.topic == msg2.topic
    assert res2.content == msg2.content
    
    multi_res = await BasicModel.get_many([msg1.id, msg2.id])
    for r in multi_res:
        assert r.id in [msg1.id, msg2.id]




@pytest.mark.asyncio
async def test_delete(simple_seeded_database):
    
    [msg1, msg2] = simple_seeded_database["messages"]  
    
    msg1_res = await BasicModel.get(msg1.id)
    assert msg1_res is not None
    assert msg1_res.id == msg1.id
    await msg1.delete()
    msg1_res = await BasicModel.get(msg1.id)
    assert msg1_res is None
    msg2_res = await BasicModel.get(msg2.id)
    assert msg2_res is not None
    assert msg2_res.id == msg2.id
    await msg2.delete()
    msg2_res = await BasicModel.get(msg2.id)
    assert msg2_res is None
    
    
@pytest.mark.asyncio
async def test_batch_delete(simple_seeded_database):
    
    [msg1, msg2] = simple_seeded_database["messages"]
    
    msgs_res = await BasicModel.all()
    assert len(msgs_res) == 2
    await BasicModel.batch_delete([msg1.id, msg2.id])
    msgs_res = await BasicModel.all()
    assert len(msgs_res) == 0
    
    
    
    
@pytest.mark.asyncio
async def test_filter_delete(simple_seeded_database):
    
    [msg1, msg2] = simple_seeded_database["messages"]
    
    msgs_res = await BasicModel.all()
    assert len(msgs_res) == 2
    await BasicModel.batch_delete(filters=lambda x: x.topic == msg1.topic)
    msgs_res = await BasicModel.all()
    assert len(msgs_res) == 1
    assert msgs_res[0].topic == msg2.topic