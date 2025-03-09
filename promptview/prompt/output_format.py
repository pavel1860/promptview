from __future__ import annotations

from typing import TYPE_CHECKING
from pydantic import BaseModel, Field, PrivateAttr
from promptview.parsers.xml_parser2 import XmlOutputParser
if TYPE_CHECKING:
    from promptview.prompt.block2 import StrBlock



class OutputModel(BaseModel):
    _tool_calls: list[BaseModel] = PrivateAttr(default=[])
    
    @classmethod
    def render(cls) -> StrBlock | None:
        return None
    
    @classmethod
    def to_block(cls) -> StrBlock:
        from promptview import block as b
        with b.title("Output format", id="output_format") as output_format:
            b += "you should use the following format for your output:"
            for field, field_info in cls.model_fields.items():
                with b.xml(field, type=field_info.annotation.__name__):
                    if field_info.description:
                        b += field_info.description
            cls.render()
            # if render_output is not None:
                # output_format.append(render_output)
            return output_format
        
    @classmethod
    def parse(cls, text: str):
        xml_parser = XmlOutputParser()
        fmt_res, fmt_actions = xml_parser.parse(f"<root>{text}</root>", [], cls)
        cls._tool_calls = fmt_actions
        return fmt_res
