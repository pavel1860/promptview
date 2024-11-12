




class DBRouter:
    
    def __init__(self):
        self._db_routers = []
        self._vectorizers = []
    
    
    def init(self, db_clients, vectorizers):
        self._db_routers = db_clients
        self._vectorizers = vectorizers
        
        
    def get_db(self):
        return self._db_routers[0]