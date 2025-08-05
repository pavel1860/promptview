# model/model_meta.py

from typing import Any, Type
from pydantic._internal._model_construction import ModelMetaclass
from promptview.model.namespace_manager2 import NamespaceManager
from promptview.model.field_parser import FieldParser
from promptview.model.relation_parser import RelationParser
# from promptview.model.vector_parser import VectorParser

class ModelMeta(ModelMetaclass, type):
    """
    Metaclass for all ORM models.
    - Handles registration of fields, relations, and vectors.
    - Sets up backend namespaces and model attributes.
    """
    def __new__(cls, name: str, bases: tuple, dct: dict[str, Any]):
        # 1. Skip processing if this is a base model
        if dct.get("_is_base", False):
            return super().__new__(cls, name, bases, dct)

        # 2. Determine database type and namespace name
        db_type = dct.get("_db_type", "postgres")
        model_name = name
        namespace_name = dct.get("_namespace_name") or cls._default_namespace_name(model_name, db_type)
        
        # ✅ If model already registered, skip parsing and just return the class
        existing_ns = NamespaceManager.get_namespace_or_none(namespace_name, db_type)
        if existing_ns and existing_ns._model_cls:
            return super().__new__(cls, name, bases, dct)

        # 3. Build or get the backend-specific namespace
        ns = NamespaceManager.build_namespace(
            model_name=namespace_name,
            db_type=db_type,
            is_versioned=dct.get("_is_versioned", False),
            is_context=dct.get("_is_context", False),
            is_repo=dct.get("_is_repo", False),
            is_artifact=dct.get("_is_artifact", False),
            repo_namespace=dct.get("_repo", None)
        )

        # 4. Build the actual model class (inherits Pydantic + this metaclass)
        cls_obj = super().__new__(cls, name, bases, dct)

        # 5. Parse scalar fields (non-relation, non-vector)
        field_parser = FieldParser(
            model_cls=cls_obj,
            model_name=model_name,
            db_type=db_type,
            namespace=ns,
            reserved_fields=set()  # optionally provide reserved words here
        )
        field_parser.parse()

        # 6. Parse relation fields
        relation_parser = RelationParser(cls_obj, ns)
        relation_parser.parse()

        # 7. VectorParser could go here if used
        # VectorParser(cls_obj, ns).parse()

        # 8. Finalize namespace registration
        ns.set_model_class(cls_obj)
        NamespaceManager.register_model_namespace(cls_obj, ns)  # ✅ REQUIRED
        cls_obj._namespace_name = namespace_name
        cls_obj._is_versioned = dct.get("_is_versioned", False)
        cls_obj._field_extras = getattr(field_parser, "field_extras", {})
        cls_obj._relations = getattr(relation_parser, "relations", {})

        return cls_obj
    
    @staticmethod
    def _default_namespace_name(model_cls_name: str, db_type: str) -> str:
        # Example: Convert CamelCase to snake_case, pluralize if needed
        from promptview.utils.string_utils import camel_to_snake
        name = camel_to_snake(model_cls_name)
        if db_type == "postgres":
            name += "s"
        return name
