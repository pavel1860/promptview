import uuid
from sqlalchemy import UUID, create_engine, Column, Integer, String, JSON, ForeignKey, DateTime, Text, Boolean, inspect
from sqlalchemy.orm import declarative_base, relationship, Session, validates
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
import os


def get_json_type(db_url):
    if db_url.startswith("postgresql"):
        return JSONB
    return JSON


HISTORY_DB_URL = os.getenv("HISTORY_DB_URL", "postgresql://snack:Aa123456@localhost:5432/snackbot")
        
json_type = get_json_type(HISTORY_DB_URL)

Base = declarative_base()




class BranchModel(Base):
    __tablename__ = "branches"
    
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship to forked message
    forked_from_message_id = Column(Integer, ForeignKey("messages.id", name="fk_branch_forked_from_message_id", ondelete="SET NULL"), nullable=True)
    forked_from_message = relationship("MessageModel", foreign_keys=[forked_from_message_id], back_populates="forked_branches")
    forked_from_message_order = Column(Integer, nullable=True)
    
    # Relationships
    turns = relationship("TurnModel", back_populates="branch", foreign_keys="TurnModel.branch_id", cascade="all, delete-orphan")    
    messages = relationship("MessageModel", back_populates="branch", foreign_keys="MessageModel.branch_id", cascade="all, delete-orphan")






class TurnModel(Base):
    __tablename__ = "turns"
    
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Branch relationship
    branch_id = Column(Integer, ForeignKey("branches.id", name="fk_turn_branch_id", ondelete="CASCADE"), nullable=False)
    branch = relationship("BranchModel", back_populates="turns", foreign_keys=[branch_id])

    # Message relationships
    messages = relationship("MessageModel", back_populates="turn", foreign_keys="MessageModel.turn_id", cascade="all, delete-orphan")
    start_message_id = Column(Integer, ForeignKey("messages.id", name="fk_turn_start_message_id", ondelete="SET NULL"), nullable=True)
    start_message = relationship("MessageModel", foreign_keys=[start_message_id])
    
    # State
    local_state = Column(json_type, default={})






class MessageModel(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    role = Column(String, nullable=False, default="user")
    name = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    blocks = Column(json_type, nullable=True)
    run_id = Column(UUID(as_uuid=True), nullable=True)
    platform_id = Column(String, nullable=True)
    ref_id = Column(String, nullable=True)
    branch_order = Column(Integer)
    
    # Branch relationship
    branch_id = Column(Integer, ForeignKey("branches.id", name="fk_message_branch_id", ondelete="CASCADE"), nullable=False)
    branch = relationship("BranchModel", back_populates="messages", foreign_keys=[branch_id])
    
    # Turn relationship
    turn_id = Column(Integer, ForeignKey("turns.id", name="fk_message_turn_id", ondelete="CASCADE"), nullable=False)
    turn = relationship("TurnModel", back_populates="messages", foreign_keys=[turn_id])
    
    # Forked branches relationship
    forked_branches = relationship("BranchModel", back_populates="forked_from_message", foreign_keys=[BranchModel.forked_from_message_id])
    
    
    
    
    
    
    
    
    
    
    
