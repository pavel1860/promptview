






class Query:
    def __init__(self, query):
        self.query = query

    def get_query(self):
        return self.query

    def __str__(self):
        return self.query