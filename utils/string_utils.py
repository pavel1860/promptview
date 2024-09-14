import re


def render_tabs(num: int):
    return "\t" * num


def add_tabs(content: str, tabs: int):
    return "\n".join([render_tabs(tabs) + c for c in content.split("\n")])



def convert_camel_to_snake(name):    
    """Convert CamelCase to snake_case"""
    s1 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name)
    return s1.lower()
