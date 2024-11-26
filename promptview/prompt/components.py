
from enum import Enum

from promptview.utils.model_utils import describe_enum


class ToolEnum(str, Enum):

    @classmethod
    def render(cls):
        return describe_enum(cls)
