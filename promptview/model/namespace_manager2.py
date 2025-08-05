# model/namespace_manager.py

from typing import Any, Dict, Type, Optional
from promptview.model.postgres2.pg_namespace import PgNamespace
from promptview.model.qdrant2.qdrant_namespace import QdrantNamespace
# from promptview.model.neo4j_namespace import Neo4jNamespace

# If you want: Registry for Postgres extensions, like 'vector' or 'uuid-ossp'
_extensions_registry = set()

class NamespaceManager:
    _registry: Dict[tuple[str, str], Any] = {}  # {(namespace_name, db_type): Namespace}
    _model_to_namespace: Dict[Type, Any] = {}   # {ModelClass: Namespace}

    @classmethod
    def build_namespace(
        cls,
        model_name: str,
        db_type: str = "postgres",
        is_versioned: bool = False,
        is_context: bool = False,
        is_repo: bool = False,
        is_artifact: bool = False,
        repo_namespace: Optional[str] = None,
    ):
        key = (model_name, db_type)
        if key in cls._registry:
            return cls._registry[key]
        
        # Backend-specific namespace construction
        if db_type == "postgres":
            ns = PgNamespace(model_name)
        elif db_type == "qdrant":
            ns = QdrantNamespace(model_name)
        # elif db_type == "neo4j":
        #     ns = Neo4jNamespace(model_name)
        else:
            raise ValueError(f"Unsupported db_type: {db_type}")
        
        cls._registry[key] = ns
        return ns

    @classmethod
    def get_namespace(cls, namespace_name: str, db_type: str = "postgres"):
        key = (namespace_name, db_type)
        ns = cls._registry.get(key)
        if ns is None:
            raise ValueError(f"Namespace '{namespace_name}' (db: {db_type}) not found in NamespaceManager.")
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
            raise ValueError(f"Namespace for model {model_cls} not found. Did you register it?")
        return ns

    @classmethod
    def register_extension(cls, db_type: str, extension: str):
        # For Postgres: CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; etc.
        _extensions_registry.add((db_type, extension))

    @classmethod
    def get_extensions(cls):
        return list(_extensions_registry)
    
    
    @classmethod
    async def drop_all_namespaces(cls, dry_run: bool = False) -> list[str]:
        """
        Drop all namespaces (tables/collections) registered in the manager.

        Args:
            dry_run: If True, return the SQL commands that would be run without executing.

        Returns:
            A list of SQL commands (if dry_run=True), or an empty list after executing.
        """
        sql_statements = []
        for (_, db_type), ns in list(cls._registry.items()):
            if hasattr(ns, "drop_namespace") and callable(ns.drop_namespace):
                if dry_run:
                    sql = await ns.drop_namespace(dry_run=True)
                    if sql:
                        sql_statements.append(sql)
                else:
                    await ns.drop_namespace(dry_run=False)
        return sql_statements

    # (Optional) For dynamic schema migration support:
    # @classmethod
    # def migrate_namespaces(cls):
    #     ...
