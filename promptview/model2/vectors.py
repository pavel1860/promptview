import numpy as np
from scipy.sparse import csr_matrix
from pydantic import AfterValidator, BeforeValidator, BaseModel, PlainSerializer
from pydantic_core import core_schema
from pydantic import GetCoreSchemaHandler

from typing import Annotated, Any, List
import ast



class Vector(np.ndarray):
    
    
    def __new__(cls, input_array, info=None):
        # Create the ndarray instance
        obj = np.asarray(input_array).view(cls)
        # Add new attribute
        return obj
    

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls._serialize
            )
        )

    @staticmethod
    def _validate(value: Any) -> "Vector":
        print(f"value: {value}")
        if isinstance(value, str):
            import ast
            value = np.array(ast.literal_eval(value))
        elif isinstance(value, list):
            value = np.array(value)
        elif isinstance(value, np.ndarray):
            pass
        else:
            raise TypeError(f"Invalid type for NDArray: {type(value)}")
        return Vector(value)

    @staticmethod
    def _serialize(instance: "Vector") -> list:
        return instance.tolist()        
        
        
class SparseVector(csr_matrix): pass