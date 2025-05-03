


from promptview.model2.postgres.sql.joins import Join


class Table:
    def __init__(self, name, alias=None):
        self.name = name
        self.alias = alias
        
        
    def __str__(self):
        return self.alias or self.name

    def __repr__(self):
        return f"<Table {self.name} AS {self.alias}>" if self.alias else f"<Table {self.name}>"




class Column:
    def __init__(self, name, table=None, alias=None):
        self.name = name
        self.table = table
        self.alias = alias
        
    def __str__(self):
        prefix = f"{str(self.table)}." if self.table else ""
        base = f"{prefix}{self.name}"
        return f"{base} AS {self.alias}" if self.alias else base

    def __repr__(self):
        return str(self)



class SelectQuery:
    def __init__(self):
        self.columns = []
        self.from_table = None
        self.joins = []
        self.where_clause = None
        self.group_by = []
        self.having = None
        self.order_by = []
        self.limit = None
        self.offset = None
        self.distinct = False
        
    
    
    def join(self, table, condition, join_type='INNER', alias=None):
        self.joins.append(Join(table, condition, join_type, alias))
        return self

    def left_join(self, table, condition, alias=None):
        return self.join(table, condition, 'LEFT', alias)

    def right_join(self, table, condition, alias=None):
        return self.join(table, condition, 'RIGHT', alias)

    def inner_join(self, table, condition, alias=None):
        return self.join(table, condition, 'INNER', alias)

        
        
        
class InsertQuery:
    def __init__(self, table):
        self.table = table
        self.columns = []
        self.values = []  # List of rows (each row is a list of values)
        self.returning = []
        self.on_conflict = None  # Optional: for UPSERT



class UpdateQuery:
    def __init__(self, table):
        self.table = table
        self.set_clauses = {}  # Dict[column] = value
        self.where_clause = None
        self.returning = []


class DeleteQuery:
    def __init__(self, table):
        self.table = table
        self.where_clause = None
        self.returning = []




