from typing import Any, Callable, Generic, List, Type
from typing_extensions import TypeVar
from promptview.model3.model3 import Model
from promptview.model3.relation_info import RelationInfo
from promptview.model.postgres.sql.queries import SelectQuery, Table, Column, NestedSubquery, Subquery
from promptview.model.postgres.sql.expressions import Eq, param, OrderBy
from promptview.model.postgres.sql.compiler import Compiler
from promptview.model.postgres.sql.json_processor import Preprocessor
from promptview.utils.db_connections import PGConnectionManager

MODEL = TypeVar("MODEL", bound=Model)

class PgSelectQuerySet(Generic[MODEL]):
    def __init__(self, model_class: Type[MODEL], query: SelectQuery | None = None, alias: str | None = None):
        self.model_class = model_class
        self.namespace = model_class.get_namespace()
        self.alias_lookup = {}
        table = Table(self.namespace.name, alias=alias or self._gen_alias(self.namespace.name))
        self.query = query or SelectQuery().from_(table)
        self.table_lookup = {str(table): table}
        # self.alias_lookup = {table.alias: self.namespace.name}
        self._params = []

    def _gen_alias(self, name: str) -> str:
        base = name[0].lower()
        alias = base
        i = 1
        while alias in self.alias_lookup:
            alias = f"{base}{i}"
            i += 1
        return alias

    @property
    def from_table(self):
        return self.query.from_table

    def select(self, *fields: str):
        if len(fields) == 1 and fields[0] == "*":
            cols = [Column(f.name, self.from_table) for f in self.namespace.iter_fields()]
        else:
            cols = [Column(f, self.from_table) for f in fields]
        self.query.select(*cols)
        return self

    def where(self, **kwargs):
        for field, value in kwargs.items():
            self.query.where.and_(Eq(Column(field, self.from_table), param(value)))
        return self

    def join(self, target: Type[Model], join_type: str = "LEFT"):
        rel = self.namespace.get_relation_by_type(target)
        if not rel:
            raise ValueError(f"No relation to {target.__name__}")
        
        target_ns = rel.foreign_cls.get_namespace()

        if rel.is_many_to_many:
            junction_ns = rel.relation_model.get_namespace()
            jt = Table(junction_ns.name, alias=self._gen_alias(junction_ns.name))
            self.query.join(jt, Eq(Column(rel.primary_key, self.from_table),
                                   Column(rel.primary_key, jt)), join_type)
            tt = Table(target_ns.name, alias=self._gen_alias(target_ns.name))
            self.query.join(tt, Eq(Column(rel.foreign_key, tt),
                                   Column(rel.foreign_key, jt)), join_type)
        else:
            tt = Table(target_ns.name, alias=self._gen_alias(target_ns.name))
            self.query.join(tt, Eq(Column(rel.foreign_key, tt),
                                   Column(rel.primary_key, self.from_table)), join_type)
        return self

    def include(self, target: Type[Model]):
        rel = self.namespace.get_relation_by_type(target)
        if not rel:
            raise ValueError(f"No relation to {target.__name__}")
        target_ns = rel.foreign_cls.get_namespace()
        nested = Column(
            rel.name,
            NestedSubquery(
                SelectQuery().from_(Table(target_ns.name)),
                rel.name,
                Column(rel.primary_key, self.from_table),
                Column(rel.foreign_key, Table(target_ns.name))
            )
        )
        self.query.columns.append(nested)
        return self

    def order_by(self, *fields: str):
        orderings = []
        for field in fields:
            direction = "ASC"
            if field.startswith("-"):
                direction = "DESC"
                field = field[1:]
            orderings.append(OrderBy(Column(field, self.from_table), direction))
        self.query.order_by_(*orderings)
        return self

    def limit(self, n: int):
        self.query.limit_(n)
        return self
    
    def render(self) -> tuple[str, list[Any]]:
        compiler = Compiler()
        processor = Preprocessor()
        compiled = processor.process_query(self.query)
        sql, params = compiler.compile(compiled)
        return sql, params

    async def execute(self) -> List[MODEL]:
        compiler = Compiler()
        processor = Preprocessor()
        compiled = processor.process_query(self.query)
        sql, params = compiler.compile(compiled)
        rows = await PGConnectionManager.fetch(sql, *params)
        return [self.model_class(**row) for row in rows]
