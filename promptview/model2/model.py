from typing import Any, Dict, Optional, Type, TypeVar, Callable, cast
from pydantic import BaseModel
from pydantic.config import JsonDict

from promptview.model2.namespace_manager import NamespaceManager
from promptview.model2.base_namespace import DatabaseType

T = TypeVar('T', bound=BaseModel)

class ModelFactory:
    """Factory for creating model decorators"""
    
    def postgres(self, namespace: Optional[str] = None, **options):
        """Create a PostgreSQL model decorator"""
        return self._create_decorator("postgres", namespace, **options)
    
    def qdrant(self, namespace: Optional[str] = None, **options):
        """Create a Qdrant model decorator"""
        return self._create_decorator("qdrant", namespace, **options)
    
    def _create_decorator(self, db_type: DatabaseType, namespace: Optional[str] = None, **options):
        """Create a model decorator for the specified database type"""
        def decorator(cls: Type[T]) -> Type[T]:
            # Get model name and namespace
            model_name = cls.__name__
            namespace_name = namespace or f"{model_name.lower()}s"
            
            # Build namespace
            ns = NamespaceManager.build_namespace(model_name, db_type)
            
            # Process fields
            for field_name, field_info in cls.model_fields.items():
                # Skip fields without a type annotation
                if field_info.annotation is None:
                    continue
                
                # Extract field metadata
                extra_json = field_info.json_schema_extra
                extra: Dict[str, Any] = {}
                
                # Convert json_schema_extra to a dictionary
                if extra_json is not None:
                    if isinstance(extra_json, dict):
                        extra = dict(extra_json)
                    elif callable(extra_json):
                        # If it's a callable, create an empty dict
                        # In a real implementation, we might want to call it
                        extra = {}
                
                # Add field to namespace
                ns.add_field(field_name, field_info.annotation, extra)
            
            # Add namespace reference to the class
            cls._namespace_name = namespace_name  # type: ignore
            
            # Add ORM methods to the class
            @classmethod
            async def initialize(cls):
                """Initialize the model (create table)"""
                ns = NamespaceManager.get_namespace(cls._namespace_name)  # type: ignore
                await ns.create_namespace()
            
            async def save(self):
                """Save the model instance to the database"""
                ns = NamespaceManager.get_namespace(self.__class__._namespace_name)  # type: ignore
                data = self.model_dump()
                result = await ns.save(data)
                # Update instance with returned data (e.g., ID)
                for key, value in result.items():
                    setattr(self, key, value)
                return self
            
            @classmethod
            async def get(cls, id: Any):
                """Get a model instance by ID"""
                ns = NamespaceManager.get_namespace(cls._namespace_name)  # type: ignore
                data = await ns.get(id)
                return cls(**data) if data else None
            
            @classmethod
            def query(cls):
                """Create a query for this model"""
                ns = NamespaceManager.get_namespace(cls._namespace_name)  # type: ignore
                return ns.query()
            
            # Add the methods to the class
            setattr(cls, 'initialize', initialize)
            setattr(cls, 'save', save)
            setattr(cls, 'get', get)
            setattr(cls, 'query', query)
            
            return cls
        
        return decorator

# Create a singleton instance
model = ModelFactory()