


class CypherExpr: pass

class CyValue(CypherExpr):
    def __init__(self, value): self.value = value
    
    def __str__(self):
        # string quoting if needed
        if isinstance(self.value, str):
            return repr(self.value)
        return str(self.value)

class CyParam(CypherExpr):
    def __init__(self, name): self.name = name
    
    def __str__(self):
        return f"${self.name}"
    
    def __repr__(self):
        return f"CyParam({self.name})"

class CyProperty(CypherExpr):
    def __init__(self, var, prop): self.var = var; self.prop = prop
    def __str__(self): return f"{self.var}.{self.prop}"

class CyEq(CypherExpr):
    def __init__(self, left, right): self.left = left; self.right = right
    def __str__(self): return f"{self.left} = {self.right}"

class CyAnd(CypherExpr):
    def __init__(self, *conds): self.conds = conds
    def __str__(self): return " AND ".join(str(c) for c in self.conds)
