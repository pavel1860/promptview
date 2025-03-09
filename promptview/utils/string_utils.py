import re
from jinja2 import Environment

def render_tabs(num: int):
    return "\t" * num


def add_tabs(content: str, tabs: int):
    return "\n".join([render_tabs(tabs) + c for c in content.split("\n")])



def convert_camel_to_snake(name):    
    """Convert CamelCase to snake_case"""
    s1 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name)
    return s1.lower()




class SafeJinjaFormatter:
    def format(self, template_string, **kwargs):
        # Create a Jinja2 environment
        env = Environment()

        # Render the template with the given kwargs
        # Use the env.from_string method to create a template from the provided string
        template = env.from_string(template_string)
        return template.render(**kwargs)
    
    def __call__(self, template_string, **kwargs):
        return self.format(template_string, **kwargs)