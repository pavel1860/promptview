



from promptview.model2.base_namespace import NSRelationInfo

class EmptyRelation(list):
    pass


class UnfetchedRelation(list):
    
    
    def __init__(self, relation: NSRelationInfo):
        self.relation = relation
        
        
    def __repr__(self) -> str:
        return f"<UnfetchedRelation {self.relation.name}>"



    def bla(self):
        return "bla"