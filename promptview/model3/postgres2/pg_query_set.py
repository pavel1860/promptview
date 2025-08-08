from functools import reduce
import json
from operator import and_
from typing import Any, Callable, Generator, Generic, List, OrderedDict, Self, Type, Union
from typing_extensions import TypeVar
from promptview.model3.model3 import Model
from promptview.model3.postgres2.rowset import RowsetNode
from promptview.model3.relation_info import RelationInfo
from ..sql.queries import CTENode, SelectQuery, Table, Column, NestedSubquery, Subquery
from ..sql.expressions import Eq, Expression, RawSQL, param, OrderBy
from ..sql.compiler import Compiler
from ..sql.json_processor import Preprocessor
from promptview.utils.db_connections import PGConnectionManager

MODEL = TypeVar("MODEL", bound=Model)



class CTERegistry:
    def __init__(self):
        # name -> (query, recursive)
        self._entries: "OrderedDict[str, tuple[Any, bool]]" = OrderedDict()
        self.recursive: bool = False

    def register_raw(self, name: str, query: Union[SelectQuery, RawSQL], *, recursive: bool = False, replace: bool = True):
        if replace or name not in self._entries:
            if name in self._entries:
                del self._entries[name]
            self._entries[name] = (query, recursive)
        if recursive:
            self.recursive = True

    def register_node(self, node: "CTENode", *, replace: bool = True):
        self.register_raw(node.name, node.query, recursive=node.recursive, replace=replace)

    def merge(self, other: "CTERegistry"):
        # last-writer-wins; preserve incoming order
        for name, (query, rec) in other._entries.items():
            self.register_raw(name, query, recursive=rec, replace=True)
        if other.recursive:
            self.recursive = True

    def import_from_select_query(self, q: SelectQuery, *, clear_source: bool = True):
        if q.ctes:
            for name, sub in q.ctes:
                # compiler expects name->query tuples; no 'recursive' per item in your current shape
                self.register_raw(name, sub, recursive=q.recursive)
        if clear_source:
            q.ctes = []
            q.recursive = False

    def to_list(self) -> list[tuple[str, Any]]:
        # drop the recursive flag per-item; Compiler already takes query.recursive
        return [(name, tup[0]) for name, tup in self._entries.items()]





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


T_co = TypeVar("T_co", covariant=True)

class QuerySetSingleAdapter(Generic[T_co]):
    def __init__(self, queryset: "PgSelectQuerySet[T_co]"):
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
  
    

class PgSelectQuerySet(Generic[MODEL]):
    def __init__(
        self, 
        model_class: Type[MODEL], 
        query: SelectQuery | None = None, 
        alias: str | None = None, 
        cte_registry: CTERegistry | None = None
    ):
        self.model_class = model_class
        self.namespace = model_class.get_namespace()
        self.alias_lookup = {}
        table = Table(self.namespace.name, alias=alias or self._gen_alias(self.namespace.name))
        self.query = query or SelectQuery().from_(table)
        self.table_lookup = {str(table): table}
        # self.alias_lookup = {table.alias: self.namespace.name}
        self._params = []
        self._cte_registry = cte_registry or CTERegistry()
        self._rowsets: "OrderedDict[str, RowsetNode]" = OrderedDict()


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
    
    def __await__(self):
        return self.execute().__await__()
    
    
    
    def _adopt_registry_from(self, other):
        # Merge if the other thing can carry CTEs
        if isinstance(other, PgSelectQuerySet):
            self._cte_registry.merge(other._cte_registry)
            other._cte_registry = self._cte_registry
        elif isinstance(other, SelectQuery):
            self._cte_registry.import_from_select_query(other, clear_source=True)
            
            
    def use_rowset(self, node: RowsetNode) -> "PgSelectQuerySet[MODEL]":
        existing = self._rowsets.get(node.name)
        if existing and existing.query is not node.query:
            # simple de-dupe rename
            suffix = len(self._rowsets) + 1
            node = RowsetNode(
                f"{node.name}_{suffix}", node.query,
                model=node.model, key=node.key,
                recursive=node.recursive, materialized=node.materialized
            )
        self._rowsets[node.name] = node
        return self

    def apply_rowset(
        self,
        node: RowsetNode,
        *,
        alias: str | None = None,
        join_type: str = "INNER",
        local_col: str | None = None,
        rowset_col: str | None = None,
        mode: str | None = None,  # "join" | "exists" | "not_exists"
    ) -> "PgSelectQuerySet[MODEL]":
        self.use_rowset(node)
        if mode in ("exists", "not_exists"):
            cte_tbl = Table(node.name, alias or self._gen_alias(node.name))
            lc, rc = (local_col, rowset_col) if (local_col and rowset_col) else self._infer_join_cols(node)
            sub = (
                SelectQuery()
                .from_(cte_tbl)
                .select(Function("COUNT", Column("*")))
            )
            sub.where.and_(Eq(Column(rc, cte_tbl), Column(lc, self.from_table)))
            cond = Function("EXISTS", sub)
            if mode == "not_exists":
                cond = Not(cond)
            self.query.where.and_(cond)
            return self

        # default: JOIN
        cte_tbl = Table(node.name, alias or self._gen_alias(node.name))
        lc, rc = (local_col, rowset_col) if (local_col and rowset_col) else self._infer_join_cols(node)
        self.query.join(cte_tbl, Eq(Column(lc, self.from_table), Column(rc, cte_tbl)), join_type)
        return self

    def _infer_join_cols(self, node: RowsetNode) -> tuple[str, str]:
        ns = self.namespace
        this_model = self.model_class
        cte_key = node.key or "id"

        # Case A: rowset is same model → join on our PK to rowset key
        if node.model is this_model:
            return (ns.primary_key, cte_key)

        # Case B: this_model declares relation to node.model
        # Meaning: the foreign (target) table has FK → this table PK
        # Join: this.PK == rowset.<target_fk>
        if node.model is not None:
            rel = ns.get_relation_by_type(node.model)
            if rel:
                return (rel.primary_key, rel.foreign_key)  # (local_col, rowset_col)

            # Case C: node.model declares relation to this_model (reverse)
            # Meaning: THIS table has FK → node PK
            # Join: this.<our_fk> == rowset.<node_pk_or_key>
            rev = node.model.get_namespace().get_relation_by_type(this_model)
            if rev:
                # rev.foreign_key is the FK column name on THIS table
                return (rev.foreign_key, cte_key)

        raise ValueError(
            f"Cannot infer join columns for rowset '{node.name}'. "
            f"Provide local_col=... and rowset_col=..., or set node.model/key."
        )
        
    def _merge_rowsets_from(self, other: "PgSelectQuerySet"):
        for node in other._rowsets.values():
            self.use_rowset(node)
        # hoist legacy `query.ctes` too, if any:
        for (name, q) in other.query.ctes:
            self.use_rowset(RowsetNode(name, q))
        other._rowsets.clear()
        other.query.ctes.clear()

    def _materialize_rowsets(self):
        # if you add dependencies later, topo-sort here
        for node in self._rowsets.values():
            self.query.with_cte(node.name, node.query, recursive=node.recursive)
        self._rowsets.clear()



    # ---------- Back-compat aliases ----------
    def use_cte(self, node_or_name, query=None, **kw):
        node = node_or_name if isinstance(node_or_name, RowsetNode) else RowsetNode(node_or_name, query, **kw)
        return self.use_rowset(node)

    def apply_cte(self, node_or_name, query=None, alias: str | None = None, **kw):
        # kw may contain alias/join_type/local_col/rowset_col/mode/model/key...
        node = node_or_name if isinstance(node_or_name, RowsetNode) else RowsetNode(node_or_name, query, model=kw.pop("model", None), key=kw.pop("key", None))
        return self.apply_rowset(node, alias=alias, **kw)

    def join_cte(self, cte_name: str, on_left: str | None = None, on_right: str | None = None, alias: str | None = None, join_type: str = "LEFT"):
        node = self._rowsets.get(cte_name)
        if node and (on_left is None or on_right is None):
            on_left, on_right = self._infer_join_cols(node)
        tbl = Table(cte_name, alias or self._gen_alias(cte_name))
        if on_left is None or on_right is None:
            raise ValueError("join_cte needs on_left and on_right (or a typed node registered under that name).")
        self.query.join(tbl, Eq(Column(on_left, self.from_table), Column(on_right, tbl)), join_type)
        return self
    
    def _apply_exists(self, node: RowsetNode, *, mode: str, local_col: str | None, rowset_col: str | None, alias: str | None):
        # Build WHERE EXISTS/NOT EXISTS (SELECT 1 FROM cte WHERE join_cond)
        from ..sql.queries import SelectQuery
        from ..sql.expressions import Function, Eq, Not

        cte_tbl = Table(node.name, alias=alias or self._gen_alias(node.name))
        local_col, rowset_col = (local_col, rowset_col) if (local_col and rowset_col) else self._infer_join_cols(node)

        sub = SelectQuery().from_(cte_tbl).select(Function("COUNT", Column("*"))).where.and_(
            Eq(Column(rowset_col, cte_tbl), Column(local_col, self.from_table))
        )
        cond = Function("EXISTS", sub)
        if mode == "not_exists":
            cond = Not(cond)
        self.query.where.and_(cond)
        return self

            


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

    def include(self, target):
        """
        Eager-load a related model or a nested query set.

        Supports:
            .include(TargetModel)
            .include(select(TargetModel).include(AnotherModel))
        """
        # --- 1) Determine the target model class ---
        from promptview.model3.postgres2.pg_query_set import PgSelectQuerySet

        if isinstance(target, PgSelectQuerySet):
            target_model_cls = target.model_class
            subq = target.query  # use the query the caller already built
        elif isinstance(target, type) and issubclass(target, Model):
            target_model_cls = target
            # build default SELECT * subquery
            target_ns = target_model_cls.get_namespace()
            target_table = Table(target_ns.name, alias=self._gen_alias(target_ns.name))
            subq = SelectQuery().from_(target_table)
            subq.select(*[Column(f.name, target_table) for f in target_ns.iter_fields()])
        else:
            raise TypeError(
                f".include() expects a Model subclass or PgSelectQuerySet, got {type(target)}"
            )

        # --- 2) Locate the relation info ---
        rel = self.namespace.get_relation_by_type(target_model_cls)
        if not rel:
            raise ValueError(f"No relation to {target_model_cls.__name__}")

        target_ns = target_model_cls.get_namespace()

        # --- 3) Many-to-Many case ---
        if rel.is_many_to_many:
            junction_ns = rel.relation_model.get_namespace()
            jt = Table(junction_ns.name, alias=self._gen_alias(junction_ns.name))
            tt = Table(target_ns.name, alias=self._gen_alias(target_ns.name))

            # If the subquery was not provided by the user, create a basic one for M:N
            if not isinstance(target, PgSelectQuerySet):
                subq = SelectQuery().from_(tt)
                subq.select(*[Column(f.name, tt) for f in target_ns.iter_fields()])

            # Always join the junction table *inside* the subquery
            subq.join(
                jt,
                Eq(Column(rel.junction_keys[1], jt), Column(target_ns.primary_key, tt))
            )

            # Build NestedSubquery correlated on the outer PK and junction key[0]
            nested = Column(
                rel.name,
                NestedSubquery(
                    subq,
                    rel.name,
                    Column(rel.primary_key, self.from_table),
                    Column(rel.junction_keys[0], jt),
                    type=rel.type
                )
            )
            nested.alias = rel.name
            self.query.columns.append(nested)

        # --- 4) One-to-One or One-to-Many case ---
        else:
            target_table = None
            if not isinstance(target, PgSelectQuerySet):
                target_table = Table(target_ns.name, alias=self._gen_alias(target_ns.name))
                
            if isinstance(target, PgSelectQuerySet):
                foreign_col_table = target.from_table
            else:
                foreign_col_table = target_table or Table(target_ns.name)

            nested = Column(
                rel.name,
                NestedSubquery(
                    subq,
                    rel.name,
                    Column(rel.primary_key, self.from_table),
                   Column(rel.foreign_key, foreign_col_table),
                    type=rel.type
                )
            )
            nested.alias = rel.name
            self.query.columns.append(nested)

        return self

    def order_by(self, *fields: str) -> "PgSelectQuerySet[MODEL]":
        orderings = []
        for field in fields:
            direction = "ASC"
            if field.startswith("-"):
                direction = "DESC"
                field = field[1:]
            orderings.append(OrderBy(Column(field, self.from_table), direction))
        self.query.order_by_(*orderings)
        return self

    def limit(self, n: int) -> "PgSelectQuerySet[MODEL]":
        self.query.limit_(n)
        return self
    
    def offset(self, n: int) -> "PgSelectQuerySet[MODEL]":
        """Skip the first `n` rows."""
        self.query.offset_(n)
        return self
    
    def distinct_on(self, *fields: str) -> "PgSelectQuerySet[MODEL]":
        """
        Postgres-specific DISTINCT ON.
        Keeps only the first row of each set of rows where the given columns are equal.
        """
        self.query.distinct_on_(*[Column(f, self.from_table) for f in fields])
        return self
    
    def first(self) -> "QuerySetSingleAdapter[MODEL]":
        """Return only the first record."""
        self.order_by(self.namespace.default_order_field)
        self.limit(1)
        return QuerySetSingleAdapter(self)

    def last(self) -> "QuerySetSingleAdapter[MODEL]":
        """Return only the last record."""
        self.order_by("-" + self.namespace.default_order_field)
        self.limit(1)
        return QuerySetSingleAdapter(self)

    def head(self, n: int) -> "PgSelectQuerySet[MODEL]":
        """
        Return the first `n` rows ordered by the model's default temporal field.
        """
        self.order_by(self.namespace.default_order_field)
        self.limit(n)
        return self

    def tail(self, n: int) -> "PgSelectQuerySet[MODEL]":
        """
        Return the last `n` rows ordered by the model's default temporal field.
        """
        self.order_by("-" + self.namespace.default_order_field)
        self.limit(n)
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
    
    
    def print(self):
        sql, params = self.render()
        print("----- QUERY -----")
        print(sql)
        print("----- PARAMS -----")
        print(params)
        return self
    
    def render(self) -> tuple[str, list[Any]]:
        # self.query.ctes = self._cte_registry.to_list()
        # self.query.recursive = self._cte_registry.recursive
        # print(self.query.ctes)
        self._materialize_rowsets()
        compiler = Compiler()
        processor = Preprocessor()
        compiled = processor.process_query(self.query)
        sql, params = compiler.compile(compiled)
        return sql, params

    async def execute(self) -> List[MODEL]:
        sql, params = self.render()
        rows = await PGConnectionManager.fetch(sql, *params)
        return [self.parse_row(dict(row)) for row in rows]







def select(model_class: Type[MODEL]) -> "PgSelectQuerySet[MODEL]":
    return model_class.query().select("*")
    # return PgSelectQuerySet(model_class).select("*")