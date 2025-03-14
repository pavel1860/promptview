from pydantic._internal._model_construction import ModelMetaclass
from pydantic import PrivateAttr, create_model, ConfigDict, BaseModel, Field
from typing import Any, Callable, Dict, ForwardRef, Generic, List, Optional, Protocol, Self, Type, TypeVar,  get_args, get_origin





class ModelMeta(ModelMetaclass, type):
    
    
    def __new__(cls, name, bases, dct):
        cls = super().__new__(cls, name, bases, dct)
        cls._fields = {}
        return cls
    
    
    
    



class Model(BaseModel, metaclass=ModelMeta):
    pass



class VectorModel(BaseModel):
    pass



class VersionedModel(BaseModel):
    pass

