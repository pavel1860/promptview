from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Generic, Literal, Type, TypeVar
from pydantic.fields import FieldInfo
import datetime as dt
from qdrant_client import models
if TYPE_CHECKING:  # pragma: nocoverage
    from .model import Model


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
        print("INIT", left, right, operator)
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
        print("OR", self, other)
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
    
    
    
    
    
    

    
    

        
# G = TypeVar("G")   
    
    
# class QueryProxy(Generic[G]):
    
#     def __getattr__(self, name):
#         if field_info:= self._cls.model_fields.get(name, None):
#             return FieldComparable(name, field_info)
#         else:
#             raise AttributeError(f"{self._cls.__name__} has no attribute {name}")
        
        
        
MODEL = TypeVar("MODEL", bound="Model")

FussionType = Literal["rff", "dbsf"]

# class VectorQuerySet:

class AllVecs:
    def __bool__(self):
        return True
    
ALL_VECS = AllVecs()


class QueryProxy(Generic[MODEL]):
    model: MODEL
    
    def __init__(self, model: MODEL):
        self.model = model
    
    def __getattr__(self, name):
        if name == "model":
            return self.model
        print("GET ATTR", name)
        if field_info:= self.model.model_fields.get(name, None):
            return FieldComparable(name, field_info)
        else:
            raise AttributeError(f"{self.model.__name__} has no attribute {name}")

class VectorQuerySet:
    query: Any
    vec: list[str] | AllVecs
    
    def __init__(self, query: str, vec: str | AllVecs=ALL_VECS):
        self.query = query
        self.vec = vec
    


class QuerySet(Generic[MODEL]):    
    model: Type[MODEL]
    _limit: int
    _offset: int
    _order_by: str | dict
    _filters: QueryFilter
    _vector_query: VectorQuerySet | None
    _unpack_result: bool = False
    
    
    def __init__(self, model: Type[MODEL]):
        self.model = model
        self._limit = None
        self._offset = None
        self._order_by = None
        self._filters = []
        self._vector_query = None
        
    def __await__(self):
        return self.execute().__await__()
    
    async def execute(self):        
        if self._vector_query:
            result = await self._execute_vector_query()
            records = [self.model.pack_search_result(r) for r in result.points]
        else:
            result = await self._execute_fetch()
            records = [self.model.pack_search_result(r) for r in result]
        
        if self._unpack_result:
            if len(records):
                return records[0]
            else:
                return None
        return records
    
    
    async def to_db_filters(self):
        ns = await self.model.get_namespace()        
        return ns.conn.transform_filters(self._filters)
    
    
    async def _execute_vector_query(self):        
        ns = await self.model.get_namespace()
        if self._vector_query.vec == ALL_VECS:
            use_vectors = [vn for vn in ns.vector_spaces]
        else:
            use_vectors = self._vector_query.vec
        vectors = await self.model._call_vectorize_query(
            self._vector_query.query, 
            use_vectors=use_vectors)        
        res = await ns.conn.query_points(
            ns.name,
            vectors=vectors,
            limit=self._limit,
            filters=self._filters,
            # threshold=threshold
            with_payload=True,
            with_vectors=True
        )
        return res
    
    async def _execute_fetch(self):
        ns = await self.model.get_namespace()
        res = await ns.conn.scroll2(
            collection_name=ns.name,
            limit=self._limit,
            filters=self._filters,
            order_by=self._order_by,
            offset=self._offset,
            # ids=ids,
            with_payload=True,
            with_vectors=True
        ) 
        return res       
    
    def similar(self, query: str, vec: list[str] | str=ALL_VECS):
        self._vector_query = VectorQuerySet(
            query=query,
            vec=vec
        )
        return self
    
    def filter(self, filter_fn: Callable[[Type[MODEL]], QueryFilter]):
        self._filters = filter_fn(QueryProxy(self.model))
        return self
        
    def limit(self, limit: int):
        self._limit = limit
        return self
    
    def topk(self, topk: int):
        self._limit = topk
        self._offset = 0
        return self
    
    def first(self):
        self._limit = 1
        self._offset = 0
        self._unpack_result = True
        return self
    
    def offset(self, offset: int):
        self._offset = offset
        return self
    
    async def all(self):
        self._limit = None
        self._offset = None
        return self
    
    def last(self):
        pass
    
    def fussion(self, *args):
        pass
    
    
    