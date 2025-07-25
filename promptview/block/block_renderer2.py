from promptview.block.block7 import  Block, BlockContext, BlockList
from promptview.block.style2 import StyleManager
from promptview.block.renderers import (
    ContentRenderer,
    RendererRegistry,
    MarkdownHeaderRenderer,
    # YamlRenderer,
    # JsonRenderer,
    # XmlRenderer,
    NumberedListRenderer,
    # BulletedListRenderer
)

# initialize global registries
style_manager = StyleManager()


style_manager.add_style(["markdown-header", "md"], {"header-format": "markdown-header"})
# style_manager.add_style(["markdown-header", "md"], {"block-format": "markdown-header"})
style_manager.add_style(["numbered-list", "list:num"], {"list-format": "numbered-list"})
style_manager.add_style(["row", "list:row"], {"list-format": "row-list"})

renderer_registry = RendererRegistry()

# register default renderers
renderer_registry.register("markdown-header", MarkdownHeaderRenderer())
# renderer_registry.register("yaml", YamlRenderer())
# renderer_registry.register("json", JsonRenderer())
# renderer_registry.register("xml", XmlRenderer())
renderer_registry.register("numbered-list", NumberedListRenderer())
renderer_registry.register("row-list", ContentRenderer())

# renderer_registry.register("bulleted-list", BulletedListRenderer())

# default fallback renderer
default_renderer = ContentRenderer()



def combine_content(left: str, right: str, sep: str):
    if left and right:
        return left + sep + right
    elif left:
        return left
    elif right:
        return right


def render(target, depth=0, style=None):
    if style is None:
        style = style_manager.resolve(target)
    if isinstance(target, BlockContext):
        return render_context(target, style, depth)
    elif isinstance(target, BlockList):
        return render_list(target, depth, style)
    elif isinstance(target, Block):
        return render_block(target, depth, style)
    else:
        raise ValueError(f"Invalid block type: {type(target)}")
    
    
def render_block(block: Block, depth: int, style: dict):
    fmt = style.get("block-format")
    renderer = renderer_registry.get(fmt) if fmt else default_renderer    
    content = renderer.render(block, block.content, style, depth)
    return content
    
def render_list(block_list: BlockList, depth: int, style: dict):
    fmt = style.get("list-format")
    renderer = renderer_registry.get(fmt) if fmt else default_renderer    
    content_list = [
        renderer.render_child(
            block_list,
            render(child, depth+1),
            style=style,
            depth=depth,
            index=index
        ) for index, child in enumerate(block_list)]
    return block_list.sep.join([c for c in content_list if c is not None])


    

def render_context(block: BlockContext, style: dict, depth):
    root_fmt = style.get("header-format")
    children_fmt = style.get("list-format")
    root_content = render_list(block.root, depth, {})
    renderer = renderer_registry.get(root_fmt) if root_fmt else default_renderer    
    root_content = renderer.render(block.root, root_content, style, depth)        
    children_content = render_list(block.children, depth+1, {"list-format": children_fmt})
    
    if block.wrap:
        root_content = block.wrap[0] + root_content + block.wrap[1]
    if block.vwrap and children_content:
        children_content = block.vwrap[0] + children_content + block.vwrap[1]
        
    return combine_content(root_content, children_content, "\n")
    





def render3(block, depth=0):
    style = style_manager.resolve(block)
    fmt = style.get("format", None)
    child_fmt = style.get("children-format", None)
    
    renderer = renderer_registry.get(fmt) if fmt else default_renderer
    
    content = ""    
    if not renderer.can_render(block):
        renderer = default_renderer
    if not block.is_empty_content:
        content = renderer.render(block, style, depth)
        if block.wrap:
            content = block.wrap[0] + content + block.wrap[1]        
    
    child_depth = depth
    if not block.is_empty_content:
        child_depth += 1
    
    if block.children:        
        chiled_content_list = []
        for child in block.children:
            
            child_content = render(child, child_depth)
            if child_fmt:
                child_renderer = renderer_registry.get(child_fmt)
                child_content = child_renderer.render(child_content, style, child_depth)            
            chiled_content_list.append(child_content)
            
        chiled_content = block.vsep.join(chiled_content_list)
        if block.vwrap:
            chiled_content = block.vwrap[0] + chiled_content + block.vwrap[1]
        content = content + "\n" + chiled_content
    return content
    
    
    



def render2(block, depth=0):
    style = style_manager.resolve(block)
    fmt = style.get("format", None)
    child_fmt = style.get("children-format", None)

    # render the block itself
    renderer = renderer_registry.get(fmt) if fmt else default_renderer
    result = renderer.render(block, style, depth, render)

    if block.children:
        # if children-format is defined, force it & skip child `format`
        if child_fmt:
            child_renderer = renderer_registry.get(child_fmt)
            result += child_renderer.render_children(block, style, depth+1, render)
        else:
            # otherwise let children pick their own styles
            for child in block.children:
                result += render(child, depth+1)

    return result
