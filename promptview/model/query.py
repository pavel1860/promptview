from enum import Enum
from pydantic.fields import FieldInfo
import datetime as dt


class FieldOp(Enum):
    GT = "gt"
    GE = "ge"
    LT = "lt"
    LE = "le"
    EQ = "eq"
    NE = "ne"
    IN = "in"
    
    

class QueryOp(Enum):
    AND = "and"
    OR = "or"    


class QueryFilter:
    
    def __init__(self, left, right, operator):
        self._left = left
        self._right = right
        self._operator = operator
        if operator not in [QueryOp.AND, QueryOp.OR]:
            if isinstance(self._left, FieldComparable):
                self.field = self._left
                self.value = self._right
            elif isinstance(self._right, FieldComparable):
                self.field = self._right
                self.value = self._left
            else:
                raise ValueError("No FieldComparable found")        
    
    def is_datetime(self):
        return self.field.type == dt.datetime   
    
        
    def __and__(self, other):
        return QueryFilter(self, other, QueryOp.AND)
    
    def __or__(self, other):
        return QueryFilter(self, other, QueryOp.OR)
    
    
    
    
    def _set_values(self):
        if isinstance(self._left, FieldComparable):
            self._field = self._left
            self._value = self._right
        elif isinstance(self._right, FieldComparable):
            self._field = self._right
            self._value = self._left
        else:
            raise ValueError("No FieldComparable found")        
        
    


class FieldComparable:
    
    def __init__(self, field_name: str, field_info: FieldInfo):
        self._filters = {}
        self.name = field_name
        self._field_info = field_info
        self.type = field_info.annotation
        
    def _validate_type(self, other):
        if self.type != type(other):
            raise ValueError(f"Cannot compare {self.name} with {other}")
        # if not isinstance(other, FieldComparable):
            # raise ValueError(f"Cannot compare {self._field_name} with {other}")

    def __gt__(self, other):
        self._validate_type(other)
        return QueryFilter(self, other, FieldOp.GT)

    def __ge__(self, other):
        self._validate_type(other)
        return QueryFilter(self, other, FieldOp.GE)

    def __lt__(self, other):
        self._validate_type(other)
        return QueryFilter(self, other, FieldOp.LT)

    def __le__(self, other):
        self._validate_type(other)
        return QueryFilter(self, other, FieldOp.LE)
        
    
    def __eq__(self, other):
        self._validate_type(other)
        return QueryFilter(self, other, FieldOp.EQ)
    
    
    def __ne__(self, other):
        self._validate_type(other)
        return QueryFilter(self, other, FieldOp.NE)

    
    def contains(self, other):
        return QueryFilter(self, other, FieldOp.IN)