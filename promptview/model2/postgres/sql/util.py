




import re

def format_function_multiline(sql: str, function_name: str, indent: int = 8) -> str:
    """
    Formats function arguments onto new lines with consistent indentation.
    e.g., json_build_object(
              'id',
              p.id,
              ...
          )
    """
    pattern = re.compile(
        rf"{function_name}\(([^()]*?(?:\([^()]*?\)[^()]*)*?)\)",
        re.DOTALL
    )

    def split_args(arg_str):
        args = []
        current = ''
        depth = 0
        for char in arg_str:
            if char == ',' and depth == 0:
                args.append(current.strip())
                current = ''
            else:
                current += char
                if char == '(':
                    depth += 1
                elif char == ')':
                    depth -= 1
        if current:
            args.append(current.strip())
        return args

    indent_spaces = ' ' * indent

    def replacer(match):
        args = split_args(match.group(1))
        joined = ",\n".join(f"{indent_spaces}{arg}" for arg in args)
        return f"{function_name}(\n{joined}\n)"

    previous = None
    while previous != sql:
        previous = sql
        sql = pattern.sub(replacer, sql)

    return sql





def print_sql(sql: str, new_line: bool = False):
    import sqlparse

    # Step 1: Format everything else
    sql = sqlparse.format(sql, reindent=True, keyword_case='upper')

    # Step 2: Apply function formatting AFTER sqlparse
    if new_line:
        for fn in ["json_agg", "json_build_object"]:
            sql = format_function_multiline(sql, fn, indent=10)

    print(sql)
