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
    
    
    
    