


from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from promptview.model2.postgres.sql.queries import Column


class Expression:
    def __and__(self, other):
        return And(self, other)

    def __or__(self, other):
        return Or(self, other)

    def __invert__(self):
        return Not(self)

    
    



class Value(Expression):
    def __init__(self, value, inline=True):
        self.value = value
        self.inline = inline
        
        
def param(value):
    return Value(value, inline=False)

class Function(Expression):
    def __init__(self, name, *args, alias=None, filter_where=None, distinct=False):
        self.name = name
        self.args = args
        self.alias = alias
        self.filter_where = filter_where
        self.distinct = distinct

    def __str__(self):
        inner = ", ".join(str(arg) for arg in self.args)
        return f"{self.name}({inner})" + (f" AS {self.alias}" if self.alias else "")



class Coalesce(Expression):
    def __init__(self, *values, alias=None):
        self.values = values
        self.alias = alias

def json_build_object(**kwargs):
    args = []
    for key, value in kwargs.items():
        args.append(Value(key))
        args.append(value)
    return Function("jsonb_build_object", *args)




class BinaryExpression(Expression):
    def __init__(self, left, operator: str, right):
        self.left = left
        self.operator = operator
        self.right = right

class Eq(BinaryExpression):
    def __init__(self, left, right):
        super().__init__(left, '=', right)

class Neq(BinaryExpression):
    def __init__(self, left, right):
        super().__init__(left, '!=', right)

class Gt(BinaryExpression):
    def __init__(self, left, right):
        super().__init__(left, '>', right)

class Gte(BinaryExpression):
    def __init__(self, left, right):
        super().__init__(left, '>=', right)

class Lt(BinaryExpression):
    def __init__(self, left, right):
        super().__init__(left, '<', right)

class Lte(BinaryExpression):
    def __init__(self, left, right):
        super().__init__(left, '<=', right)




class And(Expression):
    def __init__(self, *conditions):
        self.conditions = conditions

class Or(Expression):
    def __init__(self, *conditions):
        self.conditions = conditions

class Not(Expression):
    def __init__(self, condition):
        self.condition = condition


class OrderBy(Expression):
    def __init__(self, column: "Column", direction: str = "ASC"):
        self.column = column
        self.direction = direction.upper()



class IsNull(Expression):
    def __init__(self, value):
        self.value = value

class In(Expression):
    def __init__(self, value, options):
        self.value = value
        self.options = options  # Can be a list or subquery

class Between(Expression):
    def __init__(self, value, lower, upper):
        self.value = value
        self.lower = lower
        self.upper = upper

class Like(Expression):
    def __init__(self, value, pattern):
        self.value = value
        self.pattern = pattern





