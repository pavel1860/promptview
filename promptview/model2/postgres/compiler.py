





from promptview.model2.postgres.expressions import BinaryExpression, Value, And, Or, Not, IsNull, In, Between, Like, Function
from promptview.model2.postgres.query_builders3 import Column, DeleteQuery, InsertQuery, SelectQuery, Table, UpdateQuery, Column





    






class Compiler:
    def __init__(self):
        self.params = []
        self.param_counter = 1

    def compile(self, query):
        if isinstance(query, SelectQuery):
            return self._compile_select(query)
        elif isinstance(query, InsertQuery):
            return self._compile_insert(query)
        elif isinstance(query, UpdateQuery):
            return self._compile_update(query)
        elif isinstance(query, DeleteQuery):
            return self._compile_delete(query)
        else:
            raise TypeError(f"Unknown query type: {type(query)}")


    def add_param(self, value):
        self.params.append(value)
        placeholder = f"${self.param_counter}"
        self.param_counter += 1
        return placeholder
    
    
    
    def compile_column(self, col):
        if isinstance(col, Column):
            return str(col)
        else:
            return self.compile_expr(col)


    def compile_table(self, table):
        if isinstance(table, Table):
            return f"{table.name}{f' AS {table.alias}' if table.alias else ''}"
        return str(table)


    def compile_expr(self, expr):
        if isinstance(expr, Column):
            return self.compile_column(expr)
        elif isinstance(expr, Value):
            if expr.inline and isinstance(expr.value, str):
                return f"'{expr.value}'"
            return self.add_param(expr.value)
            return self.add_param(expr.value)
        elif isinstance(expr, BinaryExpression):
            left = self.compile_expr(expr.left)
            right = self.compile_expr(expr.right)
            return f"({left} {expr.operator} {right})"
        elif isinstance(expr, And):
            return f"({' AND '.join(self.compile_expr(c) for c in expr.conditions)})"
        elif isinstance(expr, Or):
            return f"({' OR '.join(self.compile_expr(c) for c in expr.conditions)})"
        elif isinstance(expr, Not):
            return f"(NOT {self.compile_expr(expr.condition)})"
        elif isinstance(expr, IsNull):
            return f"({self.compile_expr(expr.value)} IS NULL)"
        elif isinstance(expr, In):
            val = self.compile_expr(expr.value)
            options = ', '.join(self.add_param(opt) for opt in expr.options)
            return f"({val} IN ({options}))"
        elif isinstance(expr, Between):
            val = self.compile_expr(expr.value)
            lower = self.compile_expr(expr.lower)
            upper = self.compile_expr(expr.upper)
            return f"({val} BETWEEN {lower} AND {upper})"
        elif isinstance(expr, Like):
            val = self.compile_expr(expr.value)
            pattern = self.compile_expr(expr.pattern)
            return f"({val} LIKE {pattern})"
        # elif isinstance(expr, Function):
        #     inner = ", ".join(self.compile_expr(arg) for arg in expr.args)
        #     compiled = f"{expr.name}({inner})"
        #     if expr.alias:
        #         compiled += f" AS {expr.alias}"
        #     return compiled
        elif isinstance(expr, Function):
            inner = ", ".join(self.compile_expr(arg) for arg in expr.args)
            compiled = f"{expr.name}({inner})"
            if expr.alias:
                compiled += f" AS {expr.alias}"
            return compiled
        else:
            raise TypeError(f"Unknown expression type: {type(expr)}")

    
    def compile_joins(self, joins):
        return " ".join(
            f"{join.join_type} JOIN {self.compile_table(join.table)} ON {self.compile_expr(join.condition)}"
            for join in joins
        )

    
    
    def _compile_select(self, q: SelectQuery):
        sql = "SELECT "
        sql += "DISTINCT " if q.distinct else ""
        sql += ", ".join(self.compile_column(col) for col in q.columns or ['*'])

        sql += f"\nFROM {self.compile_table(q.from_table)}"

        if q.joins:
            sql += f"\n{self.compile_joins(q.joins)}"

        if q.where_clause:
            sql += f"\nWHERE {self.compile_expr(q.where_clause)}"

        if q.group_by:
            sql += "\nGROUP BY " + ", ".join(self.compile_column(c) for c in q.group_by)

        if q.having:
            sql += f"\nHAVING {self.compile_expr(q.having)}"

        if q.order_by:
            sql += "\nORDER BY " + ", ".join(self.compile_column(c) for c in q.order_by)

        if q.limit is not None:
            sql += f"\nLIMIT {q.limit}"

        if q.offset is not None:
            sql += f"\nOFFSET {q.offset}"

        return sql, self.params
