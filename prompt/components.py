
from enum import Enum
from promptview.utils.model_utils import describe_enum



class ToolEnum(str, Enum):

    @classmethod
    def render(self):
        return describe_enum(self)
