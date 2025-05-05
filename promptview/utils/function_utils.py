import inspect


def is_async_function(obj):
    return inspect.iscoroutinefunction(obj) or inspect.isasyncgenfunction(obj)

def get_func_args(func):
    return list(inspect.signature(func).parameters.keys())

def flatten_list(nested_list):
    flat_list = []
    for item in nested_list:
        if isinstance(item, list):
            flat_list.extend(flatten_list(item))
        else:
            flat_list.append(item)
    return flat_list

def filter_func_args(func, args):
    return {k: v for k, v in args.items() if k in get_func_args(func)}


# async def call_function(func, *args, **kwargs):
#     func_args = get_func_args(func)
#     if 'kwargs' not in func_args:
#         kwargs = filter_func_args(func, kwargs)
#     if inspect.iscoroutinefunction(func):
#         return await func(*args, **kwargs)
#     return func(*args, **kwargs)


async def call_function(func, *args, **kwargs):
    sig = inspect.signature(func)
    func_params = list(sig.parameters.values())
    
    # Filter positional args to match the number of non-keyword-only parameters
    positional_params = [p for p in func_params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    filtered_args = args[:len(positional_params)]
    
    # Filter kwargs if there's no **kwargs parameter
    if not any(p.kind == p.VAR_KEYWORD for p in func_params):
        kwargs = filter_func_args(func, kwargs)
    
    if inspect.iscoroutinefunction(func):
        return await func(*filtered_args, **kwargs)
    return func(*filtered_args, **kwargs)

def filter_args_by_exclude(args: tuple, kwargs: dict, exclude_classes: tuple[type, ...]) -> tuple[tuple, dict]:
    """
    Filter args and kwargs by excluding values of specified classes.
    
    Args:
        args: Tuple of positional arguments
        kwargs: Dictionary of keyword arguments
        exclude_classes: Tuple of classes to exclude
        
    Returns:
        Tuple of (filtered_args, filtered_kwargs)
    """
    filtered_args = tuple(arg for arg in args if not isinstance(arg, exclude_classes))
    filtered_kwargs = {k: v for k, v in kwargs.items() if not isinstance(v, exclude_classes)}
    return filtered_args, filtered_kwargs

