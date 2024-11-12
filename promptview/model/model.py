

from typing import Any, Tuple, Type, TypeVar
from pydantic import BaseModel
from pydantic import Field as PdField



def Field(
        *args, 
        partitions: str | None = None, 
        index: str | None = None,
        **kwargs
    ):
    # print(partition, index)
    
    return PdField(
        *args, 
        json_schema_extra={
            "partition_fields": partitions,
            "field_type": 'partition_fields',
            "index": index
        },
        **kwargs)



# class Vector(BaseModel):  
#     pass





class ModelMeta(type):
    
    def __new__(cls, name, bases: Tuple[Type, ...], attrs: dict):
        fields = {}    
        new_class = super().__new__(cls, name, bases, attrs)        
        return new_class
        

BaseModelMeta = type(BaseModel)



class CombinedMeta(BaseModelMeta, ModelMeta):
    pass





MODEL = TypeVar("MODEL", bound="Model")

class Model(BaseModel, metaclass=CombinedMeta):
    
        
    @staticmethod
    async def generate_namespace(self):
        pass
    
    
    @classmethod
    async def create(
        cls: Type[MODEL],
        **kwargs: Any
    ):
        instance = cls(**kwargs)
        await instance.save()
        return instance
    
    @staticmethod
    async def last(self):
        pass
    
    @staticmethod
    async def one(self):
        pass
    
    @staticmethod
    async def get_many(self):
        pass
    
    @staticmethod
    async def get_or_create(self):
        pass
    
    @staticmethod
    async def filter(self):
        pass
    
    async def save(self):
        pass


# class Asset(Model):
#     created_at: str
#     updated_at: str
#     phone_number: str
#     manager_phone_number: str


