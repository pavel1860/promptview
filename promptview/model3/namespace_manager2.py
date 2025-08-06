import sys
from typing import Any, Dict, Type, Optional
from promptview.model3.postgres2.pg_namespace import PgNamespace
from promptview.model3.qdrant2.qdrant_namespace import QdrantNamespace

_extensions_registry = set()

class NamespaceManager:
    _registry: Dict[tuple[str, str], Any] = {}
    _model_to_namespace: Dict[Type, Any] = {}

    @classmethod
    def build_namespace(cls, model_name: str, db_type: str = "postgres", **kwargs):
        key = (model_name, db_type)
        if key in cls._registry:
            return cls._registry[key]
        if db_type == "postgres":
            ns = PgNamespace(model_name)
        elif db_type == "qdrant":
            ns = QdrantNamespace(model_name)
        else:
            raise ValueError(f"Unsupported db_type: {db_type}")
        cls._registry[key] = ns
        return ns

    @classmethod
    def get_namespace(cls, namespace_name: str, db_type: str = "postgres"):
        key = (namespace_name, db_type)
        ns = cls._registry.get(key)
        if ns is None:
            raise ValueError(f"Namespace '{namespace_name}' (db: {db_type}) not found.")
        return ns

    @classmethod
    def get_namespace_or_none(cls, namespace_name: str, db_type: str = "postgres"):
        return cls._registry.get((namespace_name, db_type))

    @classmethod
    def register_model_namespace(cls, model_cls: Type, namespace: Any):
        cls._model_to_namespace[model_cls] = namespace

    @classmethod
    def get_namespace_for_model(cls, model_cls: Type):
        ns = cls._model_to_namespace.get(model_cls)
        if ns is None:
            raise ValueError(f"Namespace for model {model_cls} not found.")
        return ns


    @classmethod
    async def initialize_all(cls):
        cls.finalize()
        # 1️⃣ Create all tables first
        for ns in cls._registry.values():
            if hasattr(ns, "create_namespace"):
                await ns.create_namespace()

        # 2️⃣ Then add all foreign keys
        for ns in cls._registry.values():
            if hasattr(ns, "add_foreign_keys"):
                await ns.add_foreign_keys()

    
    @classmethod
    def finalize(cls):
        """Run any pending parsers after all models are loaded, and resolve relations."""
        for ns in cls._registry.values():
            if hasattr(ns, "_pending_field_parser"):
                ns._pending_field_parser.parse()
                del ns._pending_field_parser
            if hasattr(ns, "_pending_relation_parser"):
                ns._pending_relation_parser.parse()
                del ns._pending_relation_parser

        # NEW: Resolve foreign class forward refs
        globalns = {}
        for model_cls in cls._model_to_namespace.keys():
            globalns[model_cls.__name__] = model_cls

        for ns in cls._registry.values():
            for rel in ns._relations.values():
                try:
                    rel.resolve_foreign_cls(globalns)
                except Exception as e:
                    raise RuntimeError(f"Failed to resolve relation {rel.name} in {ns.name}: {e}")


    @classmethod
    async def drop_all_namespaces(cls, dry_run: bool = False) -> list[str]:
        sql_statements = []
        for (_, _), ns in list(cls._registry.items()):
            if hasattr(ns, "drop_namespace") and callable(ns.drop_namespace):
                if dry_run:
                    sql = await ns.drop_namespace(dry_run=True)
                    if sql:
                        sql_statements.append(sql)
                else:
                    await ns.drop_namespace(dry_run=False)
        return sql_statements



    @classmethod
    def drop_all_tables(cls):
        from promptview.model.postgres.builder import SQLBuilder        
        SQLBuilder.drop_all_tables()
        SQLBuilder.drop_enum_types()
        