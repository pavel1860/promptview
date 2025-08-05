



# promptview/utils/model_field_utils.py

from typing import Any, Dict
from pydantic.fields import FieldInfo

def unpack_extra(field_info: FieldInfo) -> dict[str, Any]:
    extra_json = field_info.json_schema_extra
    extra: Dict[str, Any] = {}
    if extra_json is not None:
        if isinstance(extra_json, dict):
            extra = dict(extra_json)
        elif callable(extra_json):
            extra = {}  # optionally call it if you want dynamic schema
    return extra
