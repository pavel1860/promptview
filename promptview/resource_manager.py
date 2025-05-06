





from typing import Type

from promptview.algebra.vectors.base_vectorizer import BaseVectorizer

VectorizerName = str

class ResourceManager:
    
    _instantiated_vectorizers: dict[VectorizerName, BaseVectorizer] = {}
    _vectorizers: dict[str, BaseVectorizer] = {}
    
    @classmethod
    def register_vectorizer(cls, name: str, vectorizer_cls: Type[BaseVectorizer]):
        # cls._vectorizers_objs[name] = vectorizer_cls
        # if vectorizer_cls in cls._vectorizers:       
        
        vectorizer = cls._instantiated_vectorizers.get(vectorizer_cls.__name__)
        if vectorizer is None:
            vectorizer = vectorizer_cls()
            cls._instantiated_vectorizers[vectorizer_cls.__name__] = vectorizer
            
        cls._vectorizers[name] = vectorizer
        
        
    