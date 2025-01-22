import uuid
from sqlalchemy import UUID, create_engine, Column, Integer, String, JSON, ForeignKey, DateTime, Text
from sqlalchemy.orm import declarative_base, relationship, Session
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
import os
from contextlib import contextmanager





def get_json_type(db_url):
    if db_url.startswith("postgresql"):
        return JSONB
    return JSON


DB_URL = os.getenv("DB_URL", "postgresql://snack:Aa123456@localhost:5432/snackbot")
        
json_type = get_json_type(DB_URL)

Base = declarative_base()



class MessageSession(Base):
    __tablename__ = "message_sessions"
    id = Column(Integer, primary_key=True)    
    branches = relationship("Branch", back_populates="session")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # main_branch_id = Column(Integer, ForeignKey("branches.id", name="fk_main_branch_id", ondelete="SET NULL"), nullable=True)
    # main_branch = relationship("Branch", foreign_keys=[main_branch_id])



class Branch(Base):
    __tablename__ = 'branches'
    
    id = Column(Integer, primary_key=True)
    # name = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    
    # The message from which this branch was created
    forked_from_message_id = Column(
        Integer, 
        ForeignKey(
            'messages.id',
            name='fk_forked_from_message_id', 
            # ondelete='CASCADE'
            ondelete='SET NULL'
        ), 
        nullable=True
    )
    forked_from_message = relationship("Message", foreign_keys=[forked_from_message_id])
    
    # All messages in this branch
    messages = relationship("Message", back_populates="branch", foreign_keys="Message.branch_id")
    
    
    session_id = Column(
        Integer,
        ForeignKey(
            "message_sessions.id", 
            name="fk_message_session_id",
            ondelete="CASCADE"
        ),
        nullable=False
    )
    session = relationship("MessageSession", back_populates="branches")
    

class Message(Base):
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    role = Column(String, nullable=False, default="user")
    prompt = Column(String, nullable=False, default="main")
    run_id = Column(UUID(as_uuid=True), default=uuid.uuid4)
    action_calls = Column(json_type, nullable=True)
    platform_uuid = Column(String, nullable=True)
    
    # The branch this Message belongs to
    branch_id = Column(
        Integer, 
        ForeignKey(
            'branches.id',
            name="fk_branch_id", 
            ondelete="CASCADE"
        ), 
        nullable=False
    )
    
    branch = relationship("Branch", back_populates="messages",
                        foreign_keys=[branch_id])    
    folked_branches = relationship("Branch", back_populates="forked_from_message",
                               foreign_keys="Branch.forked_from_message_id")
    
    # Parent Message (the Message this one was based on)
    parent_message_id = Column(Integer, ForeignKey('messages.id', ondelete="CASCADE"), nullable=True)
    parent_message = relationship("Message", remote_side=[id],
                               backref="child_messages")
    
    # def __repr__(self):
        # return f"Message(id={self.id}, content={self.content}, role={self.role}, prompt={self.prompt}, run_id={self.run_id}, action_calls={self.action_calls}, platform_uuid={self.platform_uuid})"
        # return f"Message(id={self.id}, content={self.content}, role={self.role}, prompt={self.prompt}, run_id={self.run_id}, action_calls={self.action_calls}, platform_uuid={self.platform_uuid}) forked_branches={self.folked_branches}"
        
    def render_html(self):
        def role_chip(role):
            if role == "user":
                return '<div class="role-chip user">User</div>'
            elif role == "assistant": 
                return '<div class="role-chip assistant">Assistant</div>'
            return '<div class="role-chip tool">Tool</div>'
                        
        return f"""
<style>
.message-container {{
    max-width: 800px;
    margin: 2px;
    padding: 4px;
    border-radius: 4px;
    background: #fff;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}}

.message-header {{
    display: flex;
    align-items: center;
    margin-bottom: 1px;
}}

.message-id {{
    font-size: 10px;
    color: #666;
    margin-right: 4px;
}}

.role-chip {{
    padding: 2px 6px;
    border-radius: 8px;
    font-size: 10px;
    font-weight: 500;
    margin-right: 4px;
}}

.role-chip.user {{
    background: #E3F2FD;
    color: #1976D2;
}}

.role-chip.assistant {{
    background: #ffebee;
    color: #c62828;
}}

.role-chip.tool {{
    background: #FFF3E0;
    color: #F57C00;
}}

.message-time {{
    font-size: 10px;
    color: #999;
}}

.message-content {{
    font-size: 12px;
    line-height: 0.6;
    color: #333;
    white-space: pre-wrap;
}}
</style>

<div class="message-container">
    <div class="message-header">
        <span class="message-id">#{self.id}</span>
        {role_chip(self.role)}
        <span class="message-time">{self.created_at.strftime('%m-%d %H:%M:%S')}</span>
    </div>
    <div class="message-content">
        {self.content}
    </div>
</div>
"""

    def show(self):
        from IPython.display import display, HTML
        return display(HTML(self.render_html()))

    def get_message_history(self):
        history = []
        current = self
        while current is not None:
            history.append(current)
            current = current.parent_message
        return history

# Create a new database or connect to existing one
def init_db(db_path="postgresql://snack:Aa123456@localhost:5432/snackbot"):
    # Remove existing database file if it exists
    if os.path.exists(db_path):
        os.remove(db_path)
    
    # Create new database and tables
    # engine = create_engine(f'sqlite:///{db_path}')
    engine = create_engine(db_path)
    Base.metadata.drop_all(engine)  # Drop all tables if they exist
    Base.metadata.create_all(engine)  # Create new tables
    return engine





