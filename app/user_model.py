

from promptview.conversation.alchemy_models import BaseUserModel, Base
from promptview.conversation.models import engine
from sqlalchemy import UUID, create_engine, Column, Integer, String, JSON, ForeignKey, DateTime, Text, Boolean, inspect
import os




class AppAUser(BaseUserModel):
    __mapper_args__ = {
        "polymorphic_identity": "app_a_user",
    }
    
    # Add your custom columns here:
    name = Column(String, nullable=False)
    phone_number = Column(String)
    email = Column(String)
    
    
    
    
    
    
    
    
    
    
    
async def instantiate_all_models():    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)