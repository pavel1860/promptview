import textwrap
from typing import TYPE_CHECKING, List, Set, Any, Optional, Iterator

# Placeholder for real imports
from promptview.model2 import NamespaceManager
from promptview.model2 import Turn
from promptview.model2.base_namespace import NSFieldInfo
if TYPE_CHECKING:
    from promptview.model2.base_namespace import Model

class QueryField:
    def __init__(self, field_info: NSFieldInfo):
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

    @property
    def include_in_set_query(self) -> bool:
        return self._is_dirty
    
    @property
    def include_in_insert_query(self) -> bool:
        return self._is_dirty and not self.field_info.is_key

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


class NamespaceQueryFields:
    def __init__(self, namespace, alias: Optional[str] = None, include: Optional[Set[str]] = None):
        self.namespace = namespace
        self.alias = alias
        self._fields = {field_info.name: QueryField(field_info) for field_info in namespace.iter_fields()}
        self._include = include

    @property
    def table_name(self) -> str:
        return self.namespace.table_name

    @property
    def primary_key(self) -> str:
        return self.namespace.primary_key.name

    def __getitem__(self, key: str) -> QueryField:
        return self._fields[key]

    def set(self, key: str, value: Any):
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

    def select(self, include: Set[str]):
        self._include = include

    def iter_fields(self, keys: bool = True) -> Iterator[QueryField]:
        for field in self._fields.values():
            if not keys and field.field_info.is_key:
                continue
            if self._include and field.name not in self._include:
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
        if not self._include:
            return "*"
        return_fields = [field.render_return(self.alias) for field in self.iter_fields()]
        return ", ".join(return_fields) if return_fields else "*"
    
    def build_insert_clause(self) -> str:
        return ", ".join([field.render_field(add_quotes=False) for field in self.iter_fields(keys=False) if field.include_in_insert_query])
    
    def build_values(self) -> List[Any]:
        return [field.value for field in self.iter_fields(keys=False) if field.include_in_insert_query and field.need_placeholder]

    def build_placeholders(self) -> str:
        idx = 1
        placeholders = []
        for field in self.iter_fields():
            if field.include_in_set_query:
                if field.need_placeholder:
                    placeholders.append(f'${idx}')
                    idx += 1
                else:
                    placeholders.append(field.value)
        return ", ".join(placeholders)