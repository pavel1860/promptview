
from contextvars import ContextVar
from pydantic import BaseModel, Field
from typing import Type, TypeVar, Generic

from promptview.model.model import Model
from promptview.model.vector import BaseVector


T = TypeVar('T')







# class VectorSpace:
#     _vectors: dict[str, BaseVector]
#     _models = dict[str, Type[Model]]
#     _context_fields: ContextVar[dict[str, str]] = ContextVar("_context_fields", default={})
    
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self._vectors = {}
#         self._models = {}

#     def _init(self):
#         pass
    
    
#     def register_model(self, model: Type[Model]):
#         self._models[model.__name__] = model
#         return model




class VectorSpace:
    name: str | None = None
    vectorizer: BaseVector
    _context_fields: ContextVar[dict[str, str]] = ContextVar("_context_fields", default={})
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._vectors = {}
        self._models = {}

    def _init(self):
        pass
    
    
    def register_model(self, model: Type[Model]):
        self._models[model.__name__] = model
        return model