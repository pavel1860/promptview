from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Generator, Generic, Iterator, List, Literal, Protocol, Self, Type, TypeVar
from pydantic.fields import FieldInfo
import datetime as dt
from qdrant_client import models
if TYPE_CHECKING:  # pragma: nocoverage
    from .model import Model


class FieldOp(Enum):
    RANGE = "range"
    EQ = "eq"
    NE = "ne"
    IN = "in"
    NOTIN = "notin"
    NULL = "null"
    
    

class QueryOp(Enum):
    AND = "and"
    OR = "or"    


class QueryFilter:
    
    def __init__(self, left, operator, right):
        self._left = left
        self._right = right
        self._operator = operator
        # print("INIT", left, right, operator)
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
        if other is None:
            return self
        return QueryFilter(self, QueryOp.AND, other)
    
    def __or__(self, other):
        if other is None:
            return self
        return QueryFilter(self, QueryOp.OR, other)
    
    
    
    def _set_values(self):
        if isinstance(self._left, FieldComparable):
            self._field = self._left
            self._value = self._right
        elif isinstance(self._right, FieldComparable):
            self._field = self._right
            self._value = self._left
        else:
            raise ValueError("No FieldComparable found")     
        
    def __repr__(self):
        def recurse(obj):
            if isinstance(obj, QueryFilter):
                return repr(obj)
            return repr(obj)

        left_repr = recurse(self._left)
        right_repr = recurse(self._right)

        return f"({left_repr} {self._operator.value.upper()} {right_repr})"




class RangeFilter:
    def __init__(self, ge=None, le=None, gt=None, lt=None):
        types = [type(v) for v in [ge, le, gt, lt] if v is not None]
        if not types:
            raise ValueError("At least one value must be provided")
        for t in types:
            if t != types[0]:
                raise ValueError("All values must be of the same type")
        self.value = types[0]
        self.ge = ge
        self.le = le
        self.gt = gt
        self.lt = lt        
        
        
    def __setattr__(self, name: str, value: Any) -> None:
        if name in ["ge", "le", "gt", "lt"]:            
            if value is not None and type(value) != self.value:
                raise ValueError(f"Value must be of type {self.value}")
        super().__setattr__(name, value)
        
    def __repr__(self):
        return f"RangeFilter(ge={self.ge}, le={self.le}, gt={self.gt}, lt={self.lt})"

class FieldComparable:
    
    def __init__(self, field_name: str, field_info: FieldInfo):
        self._filters = {}
        self.name = field_name
        self._field_info = field_info
        self.type = field_info.annotation
        self._query_filter = None
        
    def _validate_type(self, other):
        if self.type != type(other):
            raise ValueError(f"Cannot compare {self.name} with {other}. Expected {self.type} got {type(other)}")
        # if not isinstance(other, FieldComparable):
            # raise ValueError(f"Cannot compare {self._field_name} with {other}")

    def __gt__(self, other):
        self._validate_type(other)
        if self._query_filter is None:
            self._query_filter = QueryFilter(self, FieldOp.RANGE, RangeFilter(gt=other))
        elif self._query_filter._operator == FieldOp.RANGE:
            self._query_filter._right.gt = other
        else:
            raise ValueError(f"Cannot compare {self.name} with {other}")
        return self._query_filter
            

    def __ge__(self, other):
        print(self.name, "GE", other)
        self._validate_type(other)
        if self._query_filter is None:
            self._query_filter = QueryFilter(self, FieldOp.RANGE, RangeFilter(ge=other))
        elif self._query_filter._operator == FieldOp.RANGE:
            self._query_filter._right.ge = other
        else:
            raise ValueError(f"Cannot compare {self.name} with {other}")
        return self._query_filter
        

    def __lt__(self, other):
        self._validate_type(other)
        if self._query_filter is None:
            self._query_filter = QueryFilter(self, FieldOp.RANGE, RangeFilter(lt=other))
        elif self._query_filter._operator == FieldOp.RANGE:
            self._query_filter._right.lt = other
        else:
            raise ValueError(f"Cannot compare {self.name} with {other}")
        return self._query_filter

    def __le__(self, other):
        print(self.name, "LE", other)
        self._validate_type(other)
        if self._query_filter is None:
            self._query_filter = QueryFilter(self, FieldOp.RANGE, RangeFilter(le=other))        
        elif self._query_filter._operator == FieldOp.RANGE:
            self._query_filter._right.le = other
        else:
            raise ValueError(f"Cannot compare {self.name} with {other}")
        return self._query_filter
    
    def __eq__(self, other):
        self._validate_type(other)
        return QueryFilter(self, FieldOp.EQ, other)    
    
    def __ne__(self, other):
        self._validate_type(other)
        return QueryFilter(self, FieldOp.NE, other)
    
    # def contains(self, other):
    #     return QueryFilter(self, other, FieldOp.IN)
    
    # def any(self, other):
    #     return QueryFilter(self, other, FieldOp.IN)
    
    def isin(self, *args):        
        if type(args[0]) == list:
            other = args[0]
        elif type(args) == tuple:
            other = list(args)
        else:
            raise ValueError(f"Invalid value for any: {args}")
        return QueryFilter(self, FieldOp.IN, other)
    
    def notin(self, *args):
        if type(args[0]) == list:
            other = args[0]
        elif type(args) == tuple:
            other = list(args)
        else:
            raise ValueError(f"Invalid value for any: {args}")
        return QueryFilter(self, FieldOp.NOTIN, other)

    def isnull(self):
        return QueryFilter(self, FieldOp.NULL, None)
    
    
    def __repr__(self):
        return f"Field({self.name})"
    
    
        
MODEL = TypeVar("MODEL", bound="Model")   
    

class ModelFilterProxy(Generic[MODEL]):
    def __init__(self, cls: Type[MODEL]):
        """
        Initialize the ORM object with a table name and fields (columns).

        :param cls: class for the proxy
        :param fields: Dictionary of field names and their values
        """   
        self._cls = cls
        fields = cls.model_fields
        self._fields = fields

        # Dynamically add properties for each field to support Intellisense
        for field_name in fields.keys():
            self._add_property(field_name)

    def _add_property(self, field_name):
        """
        Add a property dynamically for a given field name.
        This ensures Intellisense recognizes the field.
        """
        def getter(self):
            return self._fields[field_name]

        def setter(self, value):
            self._fields[field_name] = value

        # Dynamically add the property to the class
        setattr(self.__class__, field_name, property(getter, setter))

    def __dir__(self):
        """
        Add dynamic fields to the list of available attributes for Intellisense.
        """
        return list(super().__dir__()) + list(self._fields.keys())

    def get_metadata(self):
        """
        Return metadata about the fields (e.g., names, types).
        """
        return {
            "fields": list(self._fields.keys()),
            "field_values": self._fields
        }    

        
        


FusionType = Literal["rff", "dbsf"]

# class VectorQuerySet:

class AllVecs:
    def __bool__(self):
        return True
    
ALL_VECS = AllVecs()


class QueryProxy(Generic[MODEL]):
    # model: Type[MODEL]
    
    def __init__(self, model: Type[MODEL]):
        self.model = model
        fields = model.model_fields
        self._fields = fields
        # for field_name in fields.keys():
        #     self._add_property(field_name)
        # self.__annotations__ = model.model_fields
        
    # def _add_property(self, field_name):
    #     """
    #     Add a property dynamically for a given field name.
    #     This ensures Intellisense recognizes the field.
    #     """
    #     def getter(self):
    #         return self._fields[field_name]

    #     def setter(self, value):
    #         self._fields[field_name] = value

    #     # Dynamically add the property to the class
    #     setattr(self.__class__, field_name, property(getter, setter))
    def _add_property(self, field_name):
        """
        Add a property dynamically for a given field name.
        This ensures Intellisense recognizes the field.
        """
        def getter(self):
            # return self._fields[field_name]
            return FieldComparable(field_name, self._fields[field_name])

        def setter(self, value):
            self._fields[field_name] = value

        # Dynamically add the property to the class
        setattr(self.__class__, field_name, property(getter, setter))
        
    def __dir__(self) -> Iterable[str]:
        # return list(super().__dir__()) + list(self.model.model_fields.keys())
        return list(super().__dir__()) + list(self._fields.keys())
    
    def __getattr__(self, name):
        # if name == "model":
        #     return self.model        
        # print("GET ATTR", name)
        if field_info:= self.model.model_fields.get(name, None):
            return FieldComparable(name, field_info)
        else:
            raise AttributeError(f"{self.model.__name__} has no attribute {name}")

class VectorQuerySet:
    query: Any
    vec: list[str] | AllVecs
    vector_lookup: dict[str, str] | None
    threshold: float | None
    
    def __init__(self, query: str, threshold: float | None = None, vec: list[str] | str | AllVecs=ALL_VECS):
        self.query = query
        if type(vec) == str:
            self.vec = [vec]
        elif type(vec) == list or vec == ALL_VECS:
            self.vec = vec # type: ignore
        else:
            raise ValueError(f"vec must be a string or list of strings, {vec}")
        self.threshold = threshold
        self.vector_lookup = None
        
    def __repr__(self):
        return f"""
            query: "{self.query}"
            vec: {self.vec}
        """
        
    def __len__(self):
        if self.vector_lookup:
            return len(self.vector_lookup)
        return 0
    
    def __iter__(self)->Iterator[tuple[str, Any]]:
        if not self.vector_lookup:
            raise ValueError("No vectors found")
        return iter(self.vector_lookup.items())
        
    
    def first(self)->tuple[str, Any]:
        if not self.vector_lookup:
            raise ValueError("No vectors found")
        return next(iter(self.vector_lookup.items()))
    
    
    
T_co = TypeVar("T_co", covariant=True)

class QuerySetSingleAdapter(Generic[T_co]):
    def __init__(self, queryset: "QuerySet[T_co]"):
        self.queryset = queryset

    def __await__(self) -> Generator[Any, None, T_co]:
        async def await_query():
            results = await self.queryset.execute()
            if results:
                return results[0]
            return None
            # raise ValueError("No results found")
            # return None
            # raise DoesNotExist(self.queryset.model)
        return await_query().__await__()  

QueryType = Literal["vector", "fusion", "id", "order", "scroll"]

class QuerySet(Generic[MODEL]):    
    model: Type[MODEL]
    query_type: QueryType
    _ids: list[str] | None
    _limit: int
    _offset: int | None
    _order_by: str | dict | None
    _filters: QueryFilter | None
    _vector_query: VectorQuerySet | None
    _unpack_result: bool = False
    _fusion: FusionType | None
    _prefetch: list[Self]
    _partitions: dict[str, str]
    
    
    def __init__(self, model: Type[MODEL], query_type: QueryType, partitions: dict[str, str] | None = None):
        self.model = model
        self.query_type = query_type
        self._limit = 10
        self._offset = None
        self._order_by = None
        self._filters = None
        self._vector_query = None
        self._prefetch = []
        self._fusion = None
        partitions = partitions or {}
        if subspace := self.get_subspace():
            partitions.update({"_subspace": subspace})
        self._partitions = partitions
        
    def __await__(self) -> Generator[Any, None, List[MODEL]]:
        return self.execute().__await__()
    
    def get_filters(self):
        if subspace:= self.get_subspace():
            return QueryFilter(FieldComparable("_subspace"), FieldOp.EQ, subspace) & self._filters
        return self._filters
    
    def get_subspace(self):
        if subspace:=self.model._subspace.default:# type: ignore
            return subspace
        return None
    
    async def execute(self) -> List[MODEL]:
        ns = await self.model.get_namespace()
        await self._recursive_vectorization()                
        result = await ns.conn.execute_query(
            ns.name,
            query_set=self
        )
        records = [self.model.pack_search_result(r) for r in result]        
        # if self._unpack_result:
        #     if len(records):
        #         return records[0]
        #     else:
        #         return None
        return records
    
    async def _get_vec_names(self)-> list[str]:
        if self._vector_query is None:            
            return []
        if type(self._vector_query.vec) == AllVecs or self._vector_query.vec == ALL_VECS:
            ns = await self.model.get_namespace()
            return [vn for vn in ns.vector_spaces]
        elif type(self._vector_query.vec) == list:
            return self._vector_query.vec
        else:
            raise ValueError(f"Invalid vector query: {self._vector_query.vec}")
        
    
    async def _recursive_vectorization(self):
        if self.query_type == "vector" and self._vector_query is not None:
            # ns = await self.model.get_namespace()
            # # if self._vector_query.vec == ALL_VECS:
            # if type(self._vector_query.vec) == AllVecs:
            #     use_vectors = [vn for vn in ns.vector_spaces]
            # else:
            #     use_vectors = self._vector_query.vec
            use_vectors = await self._get_vec_names()
            vectors = await self.model.query_embed(
                self._vector_query.query, 
                vec=use_vectors)
            self._vector_query.vector_lookup = vectors
        if self._prefetch:
            for p in self._prefetch:
                await p._recursive_vectorization()
        return True
    
    
    async def execute2(self):        
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
        # if self._vector_query.vec == ALL_VECS:
        #     use_vectors = [vn for vn in ns.vector_spaces]
        # else:
        #     use_vectors = self._vector_query.vec
        if not self._vector_query:
            raise ValueError("No vector query found")
        use_vectors = await self._get_vec_names()
        ns = await self.model.get_namespace()
        
        vectors = await self.model.query_embed(
            self._vector_query.query, 
            vec=use_vectors)        
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
        res = await ns.conn.scroll(
            collection_name=ns.name,
            limit=self._limit,
            filters=self._filters,
            # order_by=self._order_by,
            # offset=self._offset,
            # ids=ids,
            with_payload=True,
            with_vectors=True
        ) 
        return res
    
    # def get(self, id: str | None = None, ids: list[str] | None=None):
    #     if id is not None:
    #         self._ids = id
    #     elif ids is not None:
    #         self._ids = ids
    #     else:
    #         raise ValueError("Must provide id or ids")
    #     return self
    
    def similar(self, query: str, threshold: float | None = None, vec: list[str] | str | AllVecs=ALL_VECS) -> "QuerySet[MODEL]":
        self._vector_query = VectorQuerySet(
            query=query,
            threshold=threshold,
            vec=vec,
        )
        return self
    
    
    # def filter(self, filter_fn: Callable[[QueryProxy[MODEL]], QueryFilter]) -> "QuerySet[MODEL]":
    def filter(self, filter_fn: Callable[[MODEL], bool]) -> "QuerySet[MODEL]":
        query = QueryProxy[MODEL](self.model)
        if not self._filters:
            self._filters = filter_fn(query)#type: ignore
        else:
            self._filters = self._filters & filter_fn(query)#type: ignore
        return self
    
    
    
    
    # def filter(self, filter_fn: Callable[[ModelFilterProxy[MODEL]], Any]):
    #     query = ModelFilterProxy[MODEL](self.model)
    #     self._filters = filter_fn(query)
    #     return self
    
    
    #? Original
    # def filter(self, filter_fn: Callable[[Type[MODEL]], QueryFilter]):
    #     self._filters = filter_fn(QueryProxy(self.model))
    #     return self
        
    def limit(self, limit: int):
        self._limit = limit
        return self
    
    def topk(self, topk: int):
        self._limit = topk
        self._offset = 0
        return self
    
    def first(self) -> "QuerySetSingleAdapter[MODEL]":
        self._limit = 1
        self._unpack_result = True
        self._order_by = {
            "key": "created_at",
            "direction": "asc",
            "start_from": None
        }
        return QuerySetSingleAdapter(self)
    
    def last(self) -> "QuerySetSingleAdapter[MODEL]":
        self._limit = 1
        self._unpack_result = True
        self._order_by = {
            "key": "created_at",
            "direction": "desc",
            "start_from": None
        }
        return QuerySetSingleAdapter(self)
    
    def offset(self, offset: int) -> "QuerySet[MODEL]":
        if self._order_by is not None:
            raise ValueError("Cannot use offset with order_by. Use start_from instead")
        self._offset = offset
        return self
    
    # def all(self):
    #     self._limit = None
    #     self._offset = None
    #     return self
    
    
    
    def order_by(self, key, ascending: bool=False, start_from=None) -> "QuerySet[MODEL]":
        if self._offset is not None:
            raise ValueError("Cannot use order_by with offset, use start_from instead")
        self._order_by = {
            "key": key,
            "direction": "asc" if ascending else "desc",
            "start_from": start_from
        }
        return self
    
    def fusion(self, *args, type: FusionType="rff") -> "QuerySet[MODEL]":
        for arg in args:
            if isinstance(arg, QuerySet):
                self._prefetch.append(arg) # type: ignore
            else:
                raise ValueError(f"Only QuerySet allowed in prefetch. got {arg}")
            self._fusion = type
        return self
        
    
    def __repr__(self):
        def stringify_prefetch(prefetch_list, indent_level=1):
            """
            Helper function to recursively format the `prefetch` list with indentation.
            """
            indent = "    " * indent_level
            if not prefetch_list:
                return "[]"
            formatted_items = []
            for item in prefetch_list:
                if isinstance(item, QuerySet):  # If the item is another QuerySet, call its __repr__
                    formatted_items.append(item.__repr__().replace("\n", f"\n{indent}"))
                else:  # Handle other types gracefully
                    formatted_items.append(repr(item))
            return "[\n" + indent + (",\n" + indent).join(formatted_items) + "\n" + ("    " * (indent_level - 1)) + "]"
        
        # Collect fields that are not None
        fields = {
            # "model": self.model.__class__.__name__,
            # "query_type": self.query_type,
            "_limit": self._limit,
            "_offset": self._offset,
            "_order_by": self._order_by,
            "_filters": self._filters,
            "_vector_query": self._vector_query,
            "_unpack_result": self._unpack_result,
            "_fusion": self._fusion,
            "_prefetch": stringify_prefetch(self._prefetch) if self._prefetch else None,
        }
        # Format the fields dynamically, excluding None values
        formatted_fields = "\n".join(
            f"    {key}: {value}" for key, value in fields.items() if value is not None and value != []
        )
        
        return f"""
QuerySet({self.model.__name__})[{self.query_type}]:
{formatted_fields}
        """
        
        