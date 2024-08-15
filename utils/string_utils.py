


def render_tabs(num: int):
    return "\t" * num


def add_tabs(content: str, tabs: int):
    return "\n".join([render_tabs(tabs) + c for c in content.split("\n")])
