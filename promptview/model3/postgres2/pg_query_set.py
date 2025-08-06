from functools import reduce
import json
from operator import and_
from typing import Any, Callable, Generic, List, Self, Type
from typing_extensions import TypeVar
from promptview.model3.model3 import Model
from promptview.model3.relation_info import RelationInfo
from promptview.model.postgres.sql.queries import SelectQuery, Table, Column, NestedSubquery, Subquery
from promptview.model.postgres.sql.expressions import Eq, Expression, param, OrderBy
from promptview.model.postgres.sql.compiler import Compiler
from promptview.model.postgres.sql.json_processor import Preprocessor
from promptview.utils.db_connections import PGConnectionManager

MODEL = TypeVar("MODEL", bound=Model)


class QueryProxy:
    """
    Proxy for building column expressions from a model.
    Allows lambda m: m.id > 5 style filters.
    """
    def __init__(self, model_class, table):
        self.model_class = model_class
        self.table = table

    def __getattr__(self, field_name):
        return Column(field_name, self.table)
    
    

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


    def where(
        self,
        condition: Callable[[MODEL], bool] | None = None,
        # condition: Callable[[QueryProxy], Expression] | Expression | None = None,
        **kwargs: Any
    ) -> Self:
        """
        Add a WHERE clause to the query.
        condition: callable taking a QueryProxy or direct Expression
        kwargs: field=value pairs, ANDed together
        """
        expressions = []

        # Callable condition: lambda m: m.id > 5
        if condition is not None:
            if callable(condition):
                proxy = QueryProxy(self.model_class, self.from_table)
                expr = condition(proxy)
            else:
                expr = condition  # Already an Expression
            expressions.append(expr)

        # kwargs: field=value
        for field, value in kwargs.items():
            col = Column(field, self.from_table)
            expressions.append(Eq(col, param(value)))

        # Merge with AND if multiple
        if expressions:
            expr = reduce(and_, expressions)
            self.query.where &= expr

        return self

    def filter(self, condition=None, **kwargs):
        """Alias for .where()"""
        return self.where(condition, **kwargs)

    def join(self, target: Type[Model], join_type: str = "LEFT"):
        rel = self.namespace.get_relation_by_type(target)
        if not rel:
            raise ValueError(f"No relation to {target.__name__}")
        
        target_ns = rel.foreign_cls.get_namespace()

        if rel.is_many_to_many:
            junction_ns = rel.relation_model.get_namespace()
            jt = Table(junction_ns.name, alias=self._gen_alias(junction_ns.name))

            # First key connects primary model → junction
            self.query.join(
                jt,
                Eq(Column(rel.junction_keys[0], jt), Column(rel.primary_key, self.from_table)),
                join_type
            )
            # Second key connects junction → target model
            tt = Table(target_ns.name, alias=self._gen_alias(target_ns.name))
            self.query.join(
                tt,
                Eq(Column(rel.junction_keys[1], jt), Column(rel.foreign_key, tt)),
                join_type
            )
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
        target_table = Table(target_ns.name, alias=self._gen_alias(target_ns.name))

        # Build a query with all fields from target model
        subq = SelectQuery().from_(target_table)
        subq.select(*[Column(f.name, target_table) for f in target_ns.iter_fields()])

        if rel.is_many_to_many:
            junction_ns = rel.relation_model.get_namespace()
            target_ns = rel.foreign_cls.get_namespace()

            jt = Table(junction_ns.name, alias=self._gen_alias(junction_ns.name))
            tt = Table(target_ns.name, alias=self._gen_alias(target_ns.name))

            # Subquery: select all target model rows linked through junction
            subq = SelectQuery().from_(tt)
            subq.select(*[Column(f.name, tt) for f in target_ns.iter_fields()])

            # Join target to junction
            subq.join(
                jt,
                Eq(Column(rel.junction_keys[1], jt), Column(target_ns.primary_key, tt))
            )

            # Filter by matching current model's PK in junction table
            nested = Column(
                rel.name,
                NestedSubquery(
                    subq,
                    rel.name,
                    Column(self.namespace.primary_key, self.from_table),
                    Column(rel.junction_keys[0], jt),
                    type=rel.type
                )
            )
            nested.alias = rel.name
            self.query.columns.append(nested)

        else:
            nested = Column(
                rel.name,
                NestedSubquery(
                    subq,
                    rel.name,
                    Column(rel.primary_key, self.from_table),
                    Column(rel.foreign_key, target_table),
                    type=rel.type
                )
            )
            nested.alias = rel.name
            self.query.columns.append(nested)

        # # If not already grouped, group by our PK
        # if not self.query.group_by:
        #     pk = self.namespace.primary_key.name
        #     self.query.group_by = [Column(pk, self.from_table)]

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
    
    def parse_row(self, row: dict[str, Any]) -> MODEL:
        # Convert scalar columns first
        data = dict(row)

        # Process relations
        for rel_name, rel in self.namespace._relations.items():
            if rel_name not in data:
                continue
            val = data[rel_name]
            if val is None:
                continue

            # If Postgres returned JSONB as string, load it
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except json.JSONDecodeError:
                    pass  # leave as-is

            # Convert to related model(s)
            if isinstance(val, list):
                val = [rel.foreign_cls(**item) if isinstance(item, dict) else item for item in val]
            elif isinstance(val, dict):
                val = rel.foreign_cls(**val)

            data[rel_name] = val

        return self.model_class(**data)
    
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
        return [self.parse_row(dict(row)) for row in rows]







def select(model_class: Type[MODEL]) -> "PgSelectQuerySet[MODEL]":
    return PgSelectQuerySet(model_class).select("*")