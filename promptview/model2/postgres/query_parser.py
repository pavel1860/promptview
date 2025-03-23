







import json

from pydantic import BaseModel
from promptview.model2.query_filters import FieldOp, QueryFilter, QueryOp


def build_where_clause(query_filter: QueryFilter) -> str:
    """Convert QueryFilter to SQL WHERE clause."""
    if isinstance(query_filter._operator, QueryOp):
        if query_filter._operator == QueryOp.AND:
            return f"({build_where_clause(query_filter._left)} AND {build_where_clause(query_filter._right)})"
        elif query_filter._operator == QueryOp.OR:
            return f"({build_where_clause(query_filter._left)} OR {build_where_clause(query_filter._right)})"
    elif isinstance(query_filter._operator, FieldOp):
        field = query_filter.field
        field_name = f'"{field.name}"'
        
        # Get field type information
        if hasattr(field, '_field_info'):
            field_type = field._field_info.annotation
        else:
            field_type = field.type
            
        
        # Handle JSONB fields differently
        if str(field_type).startswith("dict") or (isinstance(field_type, type) and issubclass(field_type, BaseModel)):
            json_field = f"payload->'{field.name}'"
            if query_filter._operator == FieldOp.NULL:
                return f"{json_field} IS NULL"
            elif query_filter._operator == FieldOp.EQ:
                return f"{json_field} = '{json.dumps(query_filter.value)}'"
            elif query_filter._operator == FieldOp.NE:
                return f"{json_field} != '{json.dumps(query_filter.value)}'"
            elif query_filter._operator == FieldOp.IN:
                values = [json.dumps(v) for v in query_filter.value]
                return f"{json_field} = ANY(ARRAY[{', '.join(values)}])"
            elif query_filter._operator == FieldOp.NOTIN:
                values = [json.dumps(v) for v in query_filter.value]
                return f"{json_field} != ALL(ARRAY[{', '.join(values)}])"
        
        # Handle regular fields with proper type casting
        if query_filter._operator == FieldOp.NULL:
            return f"{field_name} IS NULL"
        elif query_filter._operator == FieldOp.EQ:
            if field_type is bool:
                return f"{field_name} = {str(query_filter.value).lower()}"
            elif field_type is int:
                return f"{field_name} = {query_filter.value}"
            elif field_type is str:
                return f"{field_name} = '{query_filter.value}'"
            elif field_type is dt.datetime:
                return f"{field_name} = '{query_filter.value}'"
        elif query_filter._operator == FieldOp.NE:
            if field_type is bool:
                return f"{field_name} != {str(query_filter.value).lower()}"
            elif field_type is int:
                return f"{field_name} != {query_filter.value}"
            elif field_type is str:
                return f"{field_name} != '{query_filter.value}'"
            elif field_type is dt.datetime:
                return f"{field_name} != '{query_filter.value}'"
        elif query_filter._operator == FieldOp.IN:
            if field_type is int:
                values = [str(v) for v in query_filter.value]
                return f"{field_name} = ANY(ARRAY[{', '.join(values)}])"
            else:
                values = [f"'{v}'" for v in query_filter.value]
                return f"{field_name} = ANY(ARRAY[{', '.join(values)}])"
        elif query_filter._operator == FieldOp.NOTIN:
            if field_type is int:
                values = [str(v) for v in query_filter.value]
                return f"{field_name} != ALL(ARRAY[{', '.join(values)}])"
            else:
                values = [f"'{v}'" for v in query_filter.value]
                return f"{field_name} != ALL(ARRAY[{', '.join(values)}])"
        elif query_filter._operator == FieldOp.RANGE:
            conditions = []
            if query_filter.value.gt is not None:
                if field_type is int:
                    conditions.append(f"{field_name} > {query_filter.value.gt}")
                else:
                    conditions.append(f"{field_name} > '{query_filter.value.gt}'")
            if query_filter.value.ge is not None:
                if field_type is int:
                    conditions.append(f"{field_name} >= {query_filter.value.ge}")#f"{field_name} >= to_timestamp('{query_filter.value.ge.strfmt('YYYY-MM-DD HH24:MI:SS')}')"
                # elif field_type == dt.datetime:                        
                    # conditions.append(f"{field_name} >= to_timestamp('{query_filter.value.ge.strftime('%Y-%m-%d %H:%M:%S')}')")
                else:
                    conditions.append(f"{field_name} >= '{query_filter.value.ge}'")
            if query_filter.value.lt is not None:
                if field_type is int:
                    conditions.append(f"{field_name} < {query_filter.value.lt}")
                else:
                    conditions.append(f"{field_name} < '{query_filter.value.lt}'")
            if query_filter.value.le is not None:
                if field_type is int:
                    conditions.append(f"{field_name} <= {query_filter.value.le}")
                else:
                    conditions.append(f"{field_name} <= '{query_filter.value.le}'")
            return f"({' AND '.join(conditions)})"
    return ""