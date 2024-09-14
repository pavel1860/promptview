from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel


ToolChoice = Literal['auto', 'required', 'none']