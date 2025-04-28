import textwrap
import inspect
from enum import Enum
import json
from typing import TYPE_CHECKING, List, Literal, Set, Any, Optional, Iterator
import uuid

from pydantic import BaseModel
from promptview.utils.model_utils import get_list_type, is_list_type, make_json_serializable
from promptview.model2.base_namespace import NSFieldInfo
if TYPE_CHECKING:
    from promptview.model2.base_namespace import Model
    
    
PgIndexType = Literal["btree", "hash", "gin", "gist", "spgist", "brin"]   
    
    
    
class PgFieldInfo(NSFieldInfo):
    """PostgreSQL field information"""
    index: PgIndexType | None = None
    sql_type: str
    
    SERIAL_TYPE = "SERIAL"
    
    def __init__(
        self,
        name: str,
        field_type: type[Any],
        extra: dict[str, Any] | None = None,
    ):
        super().__init__(name, field_type, extra)
        is_primary_key = extra and extra.get("primary_key", False)
        if is_primary_key and name == "id" and field_type is int:
            self.sql_type = PgFieldInfo.SERIAL_TYPE  # Use the constant from SQLBuilder
        else:            
            self.sql_type = self.build_sql_type()
        if extra and "index" in extra:
            self.index = extra["index"]
            
    def serialize(self, value: Any) -> Any:
        """Serialize the value for the database"""
        if self.is_key and self.key_type == "uuid" and value is None:
            value = str(uuid.uuid4())
        elif self.sql_type == "JSONB":
            if self.is_list:
                value = [make_json_serializable(item) if isinstance(item, dict) else item for item in value]
                value = json.dumps(value)
            elif self.field_type is BaseModel:
                value = value.model_dump()
            elif self.data_type is dict:
                value = make_json_serializable(value)
                return json.dumps(value)
                # parsed_values = {}
                # for k, v in value.items():
                #     if isinstance(v, uuid.UUID):
                #         parsed_values[k] = str(v)
                #     elif isinstance(v, dt.datetime):
                #         parsed_values[k] = v.isoformat()
                #     else:
                #         parsed_values[k] = v                                        
                # try:
                #     return json.dumps(parsed_values)
                # except Exception as e:
                #     raise ValueError(f"Failed to serialize dict: {value}") from e
                
                
        return value
    
    def get_placeholder(self, index: int) -> str:
        """Get the placeholder for the value"""
        if self.sql_type == "JSONB":
            if self.is_list:
                return f'${index}::JSONB'
            else:
                return f'${index}::JSONB'
        elif self.is_temporal:
            if self.db_type:
                return f'${index}::{self.db_type}'
            return f'${index}::TIMESTAMP'
        else:
            return f'${index}'
    
    def deserialize(self, value: Any) -> Any:
        """Deserialize the value from the database"""
        if self.is_key and self.key_type == "uuid":
            if type(value) is None:
                raise ValueError("UUID field can not be None")
            return uuid.UUID(str(value))            
        if self.is_list and type(value) is str:
            return json.loads(value)
        elif self.data_type is dict:
            return json.loads(value)
        elif self.data_type is BaseModel:
            return self.data_type.model_validate_json(value)
        elif self.is_enum and not self.is_literal:
            return self.data_type(value)
        return value
            
    
    def build_sql_type(self) -> str:
        sql_type = None
        
        # if inspect.isclass(self.data_type):
        #     if issubclass(self.data_type, BaseModel):
        #         sql_type = "JSONB"
        #     elif issubclass(self.data_type, Enum):
        #         sql_type = "TEXT" 
        if self.db_type:
            sql_type = self.db_type               
        elif self.is_temporal:
            sql_type = "TIMESTAMP"
        elif self.is_enum:
            sql_type = self.enum_name
        elif self.is_enum:
            sql_type = "TEXT"
        elif self.data_type is int:
            sql_type = "INTEGER[]" if self.is_list else "INTEGER"
        elif self.data_type is float:
            sql_type = "FLOAT[]" if self.is_list else "FLOAT"
        elif self.data_type is str:
            sql_type = "TEXT[]" if self.is_list else "TEXT"
        elif self.data_type is bool:
            sql_type = "BOOLEAN[]" if self.is_list else "BOOLEAN"
        elif self.data_type is uuid.UUID:
            sql_type = "UUID[]" if self.is_list else "UUID"
        elif self.data_type is dict:
            sql_type = "JSONB"
        elif issubclass(self.data_type, BaseModel):
            sql_type = "JSONB"
        elif issubclass(self.data_type, Enum):
            sql_type = "TEXT"        
                
        
        if sql_type is None:
            raise ValueError(f"Unsupported field type: {self.data_type}")
        return sql_type
    
    
    @classmethod
    def to_sql_type(cls, field_type: type[Any], extra: dict[str, Any] | None = None) -> str:
        """Map a Python type to a SQL type"""
        db_field_type = None
        if is_list_type(field_type):
            list_type = get_list_type(field_type)
            if list_type is int:
                db_field_type = "INTEGER[]"
            elif list_type is float:
                db_field_type = "FLOAT[]"
            elif list_type is str:
                db_field_type = "TEXT[]"
            elif inspect.isclass(list_type):
                if issubclass(list_type, BaseModel):
                    db_field_type = "JSONB"                        
        else:
            if extra and extra.get("db_type"):
                custom_type = extra.get("db_type")
                if type(custom_type) != str:
                    raise ValueError(f"Custom type is not a string: {custom_type}")
                db_field_type = custom_type
            elif field_type == bool:
                db_field_type = "BOOLEAN"
            elif field_type == int:
                db_field_type = "INTEGER"
            elif field_type == float:
                db_field_type = "FLOAT"
            elif field_type == str:
                db_field_type = "TEXT"
            elif field_type == dt.datetime:
                # TODO: sql_type = "TIMESTAMP WITH TIME ZONE"
                db_field_type = "TIMESTAMP"
            elif isinstance(field_type, dict):
                db_field_type = "JSONB"
            elif isinstance(field_type, type):
                if issubclass(field_type, BaseModel):
                    db_field_type = "JSONB"
                if issubclass(field_type, Enum):
                    db_field_type = "TEXT"                                        
        if db_field_type is None:
            raise ValueError(f"Unsupported field type: {field_type}")
        return db_field_type
    
    def __repr__(self) -> str:
        params = self._param_repr_list()
        return f"PgFieldInfo(name={self.name}, data_type={self.data_type.__name__}, sql_type={self.sql_type}, {', '.join(params)})"


class QueryField:
    def __init__(self, field_info: PgFieldInfo):
        self.field_info = field_info
        self._value: Optional[Any] = None
        self._custom_value: Optional[str] = None
        self._label: Optional[str] = None
        self._is_dirty: bool = False

    @property
    def name(self) -> str:
        return self.field_info.name

    @property
    def value(self) -> Any: 
        return self._custom_value or self._value

    @property
    def need_placeholder(self) -> bool:
        return self._custom_value is None
    
    def is_input(self, key: bool = True):
        if not key and self.field_info.is_key:
            return False
        return self._is_dirty
            

    @property
    def include_in_set_query(self) -> bool:
        return self._is_dirty
    
    @property
    def include_in_insert_query(self) -> bool:
        return self._is_dirty and not self.field_info.is_key
    
    @property
    def output_name(self) -> str:
        return self._label or self.name

    def label(self, label: str):
        self._label = label

    def set(self, value: Any):
        self._value = self.field_info.serialize(value)
        self._is_dirty = True

    def override(self, value: str):
        self._custom_value = value
        self._is_dirty = True

    def get_placeholder(self, idx: int) -> str:
        return self._custom_value or self.field_info.get_placeholder(idx)

    def render_field(self, alias: Optional[str] = None, add_quotes: bool = True) -> str:
        field_str = f'"{self.name}"' if add_quotes else self.name
        return f'{alias}.{field_str}' if alias else field_str

    def render_return(self, alias: Optional[str] = None) -> str:
        field_str = self._label or self.render_field(alias)
        return field_str

    def render_select(self, idx: int, alias: Optional[str] = None) -> tuple[str, int]:
        field_str = self.render_field(alias)
        if self._label:
            field_str += f' AS {self._label}'
        return field_str, idx

    def render_set(self, idx: int, alias: Optional[str] = None) -> tuple[str, int]:
        field_str = self.render_field(alias, add_quotes=False)
        if self._custom_value:
            return f'{field_str} = {self._custom_value}', idx
        else:
            return f'{field_str} = ${idx}', idx + 1
        
    def __repr__(self) -> str:
        return f"QueryField(name={self.name}, value={self.value}, is_dirty={self._is_dirty})"


class NamespaceQueryFields:
    """
    A class that represents the instantiated fields of a namespace.
    the select parameter is the set of fields to select from the query.
    the setting the values of the fields will include them in the insert and update queries.
    
    """
    def __init__(self, namespace, alias: Optional[str] = None, select: Optional[Set[str]] = None):
        self.namespace = namespace
        self.alias = alias
        self._fields = {field_info.name: QueryField(field_info) for field_info in namespace.iter_fields()}
        self._select = select

    @property
    def table_name(self) -> str:
        return self.namespace.table_name

    @property
    def primary_key(self) -> str:
        return self.namespace.primary_key.name
    
    def get_inputs(self, key: bool = True) -> list[Any]:
        return [field for field in self.iter_fields() if field.is_input(key)]
    
    def get_outputs(self) -> list[Any]:
        return [field for field in self.iter_fields()]

    def __getitem__(self, key: str) -> QueryField:
        return self._fields[key]

    def set(self, key: str, value: Any):
        """set the value of a field, this will include the field in the insert and update queries"""
        if key not in self._fields:
            raise KeyError(f"Field {key} not found in namespace.")
        self._fields[key].set(value)
        
    def set_model(self, model: "Model"):
        for key, value in model.model_dump(exclude_none=True).items():
            self._fields[key].set(value)

    def override(self, key: str, value: str):
        if key not in self._fields:
            raise KeyError(f"Field {key} not found in namespace.")
        self._fields[key].override(value)

    def select(self, select: Set[str]):
        self._select = select

    def iter_fields(self, keys: bool = True, do_select: bool = True) -> Iterator[QueryField]:
        for field in self._fields.values():
            if not keys and field.field_info.is_key:
                continue
            if do_select and self._select and field.name not in self._select:
                continue
            yield field

    def build_clause(self, render_func: str) -> str:
        idx = 1
        parts = []
        for field in self.iter_fields():
            if getattr(field, "include_in_set_query", True):
                part, idx = getattr(field, render_func)(idx, self.alias)
                parts.append(part)
        return ", \n".join(parts)
    

    def build_returning_clause(self) -> str:
        if not self._select:
            return "*"
        return_fields = [field.render_return(self.alias) for field in self.iter_fields()]
        return ", ".join(return_fields) if return_fields else "*"
    
    def build_select_clause(self, new_line: bool = True) -> str:
        if not self._select:
            return "*"
        delimiter = ", \n" if new_line else ", "
        return_fields = [field.render_return(self.alias) for field in self.iter_fields()]
        return delimiter.join(return_fields) if return_fields else "*"
    
    def build_insert_clause(self) -> str:
        return ", ".join([field.render_field(add_quotes=False) for field in self.iter_fields(keys=False, do_select=False) if field.include_in_insert_query])
    
    # def build_select_clause(self) -> str:
    #     return ", ".join([field.render_field(add_quotes=False) for field in self.iter_fields(keys=False) if field.include_in_select_query])
    
    def build_values(self) -> List[Any]:
        return [field.value for field in self.iter_fields(keys=False) if field.include_in_insert_query and field.need_placeholder]

    def build_placeholders(self) -> str:
        idx = 1
        placeholders = []
        for field in self.iter_fields(do_select=False):
            if field.include_in_set_query:
                if field.need_placeholder:
                    placeholders.append(f'${idx}')
                    idx += 1
                else:
                    placeholders.append(field.value)
        return ", ".join(placeholders)