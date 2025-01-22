from typing import Literal, Union
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func, literal_column, create_engine
import os

from promptview.conversation.models import Branch, MessageSession, Base, Message

MsgRole = Literal["user", "assistant", "tool"]


class MessageList(list):
    
    
    def render_html(self):
        html_str = f"""<html>
<div style="display: flex; flex-direction: column; width: 400px; margin: 0;">
    {"".join([m.render_html() for m in self])}
</div>
</html>"""
        return html_str
    
    def show(self):
        from IPython.display import display, HTML        
        # display()
        return HTML(self.render_html())


class History:
    
    def __init__(self, db_url: str | None = None) -> None:
        DB_URL = os.getenv("DB_URL", "postgresql://snack:Aa123456@localhost:5432/snackbot")
        self._engine = create_engine(db_url or DB_URL)
        SessionLocal = sessionmaker(bind=self._engine)
        self._conn_session = SessionLocal()        
        self._branch: Branch | None = None
        self._session: MessageSession | None = None
        # self.context = HistoryContext(self.conn_session)
    
    
    def init_main(self):
        session = self.last_session()    
        if session is None:
            session = self.create_session()
        self._session = session
        self._branch = self.first_branch()
        
    def init_last(self):
        self._session = self.last_session()
        self._branch = self.last_branch()
            
    
    def last_session(self):
        return self._query(MessageSession).order_by(MessageSession.created_at.desc()).first()        
    
    def last_branch(self):
        if self._session is None:
            raise ValueError("Session not set")
        return self._session.branches[-1]
    
    def first_branch(self):
        if self._session is None:
            raise ValueError("Session not set")
        return self._session.branches[0]
        
        
    def _query(self, _entity):
        return self._conn_session.query(_entity)
    
    def _add(self, _entity):
        self._conn_session.add(_entity)
        self._conn_session.commit()
        
    def _add_all(self, _entities):
        self._conn_session.add_all(_entities)
        self._conn_session.commit()
        
    def create_all(self):
        Base.metadata.create_all(bind=self._engine)
        
    def drop_all(self):
        Base.metadata.drop_all(bind=self._engine)
                
    def list_sessions(self):
        return self._query(MessageSession).all()
    
    def list_branches(self):
        if self._session is None:
            raise ValueError("Session not set")
        return self._session.branches
        # return self._query(Branch).all()
    
    def create_session(self, checkout: bool=True):
        branch = Branch(forked_from_message_id=None)
        new_session = MessageSession(
            branches=[branch]
        )
        if checkout:
            self._session = new_session
            self._branch = branch
        self._add_all([branch, new_session])   
        return new_session
    
    def set_session(self, session: MessageSession | None = None, id: int | None = None):
        if session is None and id is None:
            raise ValueError("Session or id must be set")
        if session is None:
            session = self._query(MessageSession).filter_by(id=id).first()
            if not session:
                raise ValueError("Session not found")
        self._session = session        
    
    def set_branch(self, branch: Branch | None = None, id: int | None = None):
        if branch is None and id is None:
            raise ValueError("Branch or id must be set")
        if branch is None:
            branch = self._query(Branch).filter_by(id=id).first()
            if not branch:
                raise ValueError("Branch not found")
        self._branch = branch
        return branch
    
    def create_message(self, content, role: MsgRole="user", prompt: str | None=None, run_id=None, action_calls=None, platform_uuid=None, branch_id=None):
        last_message = None
        if branch_id is None:
            if self._branch is None:
                raise ValueError("Branch not set")
            branch_id = self._branch.id
            if self._branch.messages:
                last_message = self._branch.messages[-1]
            else:
                if self._branch.forked_from_message:
                    last_message = self._branch.forked_from_message
        message = Message(
            content=content,
            role=role,
            prompt=prompt,
            run_id=run_id,
            action_calls=action_calls,
            platform_uuid=platform_uuid,
            branch_id=branch_id,
            parent_message = last_message
        )
        self._add(message)
        return message
    
    
    def create_branch(self, from_message: Message, checkout: bool=True):
        if self._session is None:
            raise ValueError("Session not set")
        branch = Branch(forked_from_message=from_message)
        self._session.branches.append(branch)
        self._add(branch)
        if checkout:
            self._branch = branch
        return branch
        
    def _message_cte(self,message_id: int, limit: int=1):
        m = Message.__table__        
        cte = (
            select(
                m.c.id.label("id"),
                m.c.parent_message_id.label("parent_message_id"),
                literal_column("1").label("depth")
            )
            .where(m.c.id == message_id)
            .cte("parent_ids", recursive=True)
        )
        # Recursive union: follow parent_message_id -> id
        alias_m = m.alias("msg_parent")
        cte = cte.union_all(
            select(
                alias_m.c.id,
                alias_m.c.parent_message_id,
                (cte.c.depth + 1).label("depth")
            )
            .where(alias_m.c.id == cte.c.parent_message_id)
            .where(cte.c.depth < limit)
        )

        # stmt = select(cte.c.id, cte.c.depth).order_by(cte.c.depth)
        stmt = select(Message).join(cte, Message.id == cte.c.id).order_by(Message.created_at.asc())
        return self._conn_session.execute(stmt).all()
    
    def last(self, limit: int=10):
        if not self._branch:
            raise ValueError("Branch not set")
        if not self._branch.messages:
            return MessageList([])
        message_id = self._branch.messages[-1].id
        messages = self._message_cte(message_id, limit)
        return MessageList([m[0] for m in messages])
        
    def show_last(self, limit: int=10):
        messages = self.last(limit)
        return 
    
    def all_last(self, limit: int=10):
        messages = self._query(Message).order_by(Message.created_at.desc()).limit(limit).all()
        return MessageList(messages)
    
    def last_one(self):
        if not self._branch:
            raise ValueError("Branch not set")
        return self._branch.messages[-1]
    
    def all_last_one(self):
        msgs = self.all_last(1)
        if msgs:
            return msgs[0]
        return None    
    
    
    def delete(self, item: Union[Message, MessageSession, Branch, None] = None, id: int | None = None):
        if item is None and id is None:
            raise ValueError("Item or id must be set")
        if item is None:
            raise ValueError("Must provide item when id is None")

        if isinstance(item, Message):
            return self.delete_message(item, id)
        elif isinstance(item, MessageSession):
            return self.delete_session(item, id)
        elif isinstance(item, Branch):
            return self.delete_branch(item, id)
        else:
            raise ValueError(f"Unsupported item type: {type(item)}")

    def delete_message(self, message: Message | None = None, id: int | None = None):
        if message is None and id is None:
            raise ValueError("Message or id must be set")
        if message is None:
            message = self._query(Message).filter_by(id=id).first()
            if not message:
                raise ValueError("Message not found")
        else:
            # Use the passed message object's id
            message = self._query(Message).filter_by(id=message.id).first()
            if not message:
                raise ValueError("Message not found")
            
        self._conn_session.delete(message)
        self._conn_session.commit()
        return message


    def delete_session(self, session: MessageSession | None = None, id: int | None = None):
        if session is None and id is None:
            raise ValueError("Session or id must be set")
        
        if session is None:
            session = self._query(MessageSession).filter_by(id=id).first()
            if not session:
                raise ValueError("Session not found")
        else:
            # Use the passed session object's id
            session = self._query(MessageSession).filter_by(id=session.id).first()
            if not session:
                raise ValueError("Session not found")
        
        # First delete all branches associated with this session
        for branch in session.branches:
            self._conn_session.delete(branch)
        
        # Then delete the session
        self._conn_session.delete(session)
        
        try:
            self._conn_session.commit()
        except Exception as e:
            self._conn_session.rollback()
            raise e
        
        return session
    
    
    def delete_branch(self, branch: Branch | None = None, id: int | None = None):
        if branch is None and id is None:
            raise ValueError("Branch or id must be set")
        if branch is None:
            branch = self._query(Branch).filter_by(id=id).first()
            if not branch:
                raise ValueError("Branch not found")
        else:
            # Use the passed branch object's id
            branch = self._query(Branch).filter_by(id=branch.id).first()
            if not branch:
                raise ValueError("Branch not found")
            
        self._conn_session.delete(branch)
        self._conn_session.commit()
        return branch
    