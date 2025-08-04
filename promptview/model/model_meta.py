# model/model_meta.py

from typing import Any, Type
from pydantic._internal._model_construction import ModelMetaclass
from promptview.model.namespace_manager import NamespaceManager
from promptview.model.field_parser import FieldParser
# from promptview.model.relation_parser import RelationParser  # Next step
# from promptview.model.vector_parser import VectorParser      # Next step

class ModelMeta(ModelMetaclass, type):
    """Metaclass for Model: orchestrates namespace, field, relation, and vector registration."""

    def __new__(cls, name: str, bases: tuple, dct: dict[str, Any]):
        # Step 1: Skip base model
        if dct.get("_is_base", False):
            return super().__new__(cls, name, bases, dct)

        # Step 2: Determine namespace parameters
        model_name = name
        db_type = dct.get("_db_type", "postgres")
        namespace_name = dct.get("_namespace_name") or cls._default_namespace_name(model_name, db_type)

        # Step 3: Build or resolve namespace
        ns = NamespaceManager.build_namespace(
            model_name=namespace_name,
            db_type=db_type,
            # Additional flags (is_versioned, etc.) could go here
        )

        # Step 4: Build the Pydantic class with this metaclass
        cls_obj = super().__new__(cls, name, bases, dct)

        # Step 5: Field parsing (relations and vectors to follow)
        field_parser = FieldParser(
            model_cls=cls_obj,
            model_name=model_name,
            db_type=db_type,
            namespace=ns,
            reserved_fields=set(),  # Provide reserved fields as needed
        )
        field_parser.parse()

        # Step 6: RelationParser, VectorParser (to be integrated next)
        # RelationParser(cls_obj, ns).parse()
        # VectorParser(cls_obj, ns).parse()

        # Step 7: Finalize and register model class
        ns.set_model_class(cls_obj)
        cls_obj._namespace_name = namespace_name
        # Set any other required class attributes...

        return cls_obj

    @staticmethod
    def _default_namespace_name(model_cls_name: str, db_type: str) -> str:
        # Example: convert "MyModel" to "my_models" for postgres
        from promptview.utils.string_utils import camel_to_snake
        if db_type == "postgres":
            return camel_to_snake(model_cls_name) + "s"
        return model_cls_name
