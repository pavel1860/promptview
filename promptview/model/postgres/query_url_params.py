import datetime as dt
from typing import Any, List, Type

from promptview.model.postgres.sql.queries import Column, Table
from promptview.model.postgres.sql.expressions import Eq, Gte, Lte, Gt, Lt, And, Neq, param
# (adjust imports as needed for your project)

# def parse_query_params(model_class, conditions: list[list[Any]]):
#     """
#     Parse a list of query conditions into a combined SQL expression.

#     Example input:
#     conditions = [
#         ["test", "==", 1],
#         ["score", ">=", 0.9],
#         ["createdAt", "<", "2024-01-01"],
#     ]
#     Returns an Expression suitable for .where() in your ORM.
#     """
#     namespace = model_class.get_namespace()
#     table = namespace.table_name

#     # Compose individual expressions
#     exprs = []
#     for condition in conditions:
#         if len(condition) != 3:
#             raise ValueError(f"Invalid condition: {condition}")
#         field, operator, value = condition
#         field_info = namespace.get_field(field, throw_error=True)
#         column = Column(field_info.name, table)

#         # Type conversion based on field info
#         if field_info.is_temporal:
#             if isinstance(value, str):
#                 try:
#                     value = dt.datetime.fromisoformat(value)
#                 except Exception:
#                     raise ValueError(f"Invalid datetime format: {value}")
#         elif field_info.is_enum:
#             # TODO: map value to enum, if needed
#             value = value
#         elif field_info.data_type is float:
#             value = float(value)
#         elif field_info.data_type is int:
#             value = int(value)
#         # else leave as-is (str, etc.)

#         # Build expression
#         if operator == "==":
#             exprs.append(Eq(column, value))
#         elif operator == ">=":
#             exprs.append(Gte(column, value))
#         elif operator == "<=":
#             exprs.append(Lte(column, value))
#         elif operator == ">":
#             exprs.append(Gt(column, value))
#         elif operator == "<":
#             exprs.append(Lt(column, value))
#         else:
#             raise ValueError(f"Unsupported operator: {operator}")

#     # Combine with AND (can extend to support OR if desired)
#     if not exprs:
#         return None
#     elif len(exprs) == 1:
#         return exprs[0]
#     else:
#         # Chained And: And(expr1, expr2, ...)
#         return And(*exprs)





def parse_query_params(model_class, conditions: list[list[Any]], table: Table | None = None):
    """
    Parse a list of query conditions into a combined SQL expression.
    """
    namespace = model_class.get_namespace()
    
    if table is None:
        table = Table(namespace.table_name)

    exprs = []
    for condition in conditions:
        if len(condition) != 3:
            raise ValueError(f"Invalid condition: {condition}")
        field, operator, value = condition

        # -- This is the critical line --
        field_info = namespace.get_field(field, throw_error=True)
        column = Column(field_info.name, table)  # Always a Column object!

        # --- Type conversion ---
        # You can expand this if needed
        if field_info.is_temporal and isinstance(value, str):
            try:
                value = dt.datetime.fromisoformat(value)
            except Exception:
                raise ValueError(f"Invalid datetime format: {value}")

        elif field_info.is_enum:
            value = value  # Enum conversion here if needed
        elif field_info.data_type is float:
            value = float(value)
        elif field_info.data_type is int:
            value = int(value)
        # else: leave str
        value = param(value)
        # --- Build expression ---
        if operator == "==":
            exprs.append(Eq(column, value))
        elif operator == ">=":
            exprs.append(Gte(column, value))
        elif operator == "<=":
            exprs.append(Lte(column, value))
        elif operator == ">":
            exprs.append(Gt(column, value))
        elif operator == "<":
            exprs.append(Lt(column, value))
        elif operator == "!=":
            exprs.append(Neq(column, value))
        else:
            raise ValueError(f"Unsupported operator: {operator}")

    # Combine with AND
    if not exprs:
        return None
    elif len(exprs) == 1:
        return exprs[0]
    else:
        return And(*exprs)
