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




