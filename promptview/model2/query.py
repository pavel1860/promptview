from typing import Generic, Type, TypeVar
from promptview.model2.fields import Model
from promptview.model2.namespace_manager import NamespaceManager
from promptview.model2.base_namespace import Namespace





MODEL = TypeVar("MODEL", bound="Model")   


class QuerySet(Generic[MODEL]):
    _model: Type[MODEL]
    _namespace: Namespace
    
    def __init__(self, model: Type[MODEL], namespace: Namespace):
        self._model = model
        self._namespace = namespace
    
    
    def __await__(self):
        return self.execute().__await__()

    
    
# class Query(Generic[MODEL]):
#     _model: Type[MODEL]
        
#     def __init__(self, model: Type[MODEL]):
#         self._model = model


def query(model: Type[MODEL]) -> QuerySet:
    ns = NamespaceManager.get_namespace(model.__name__)
    return QuerySet(model, ns)
    
    
    
    