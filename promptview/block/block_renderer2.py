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



style_manager.add_style("markdown-header", {"format": "markdown-header"})
style_manager.add_style("numbered-list", {"children-format": "numbered-list"})

renderer_registry = RendererRegistry()

# register default renderers
renderer_registry.register("markdown-header", MarkdownHeaderRenderer())
# renderer_registry.register("yaml", YamlRenderer())
# renderer_registry.register("json", JsonRenderer())
# renderer_registry.register("xml", XmlRenderer())
renderer_registry.register("numbered-list", NumberedListRenderer())
# renderer_registry.register("bulleted-list", BulletedListRenderer())

# default fallback renderer
default_renderer = ContentRenderer()



def render(block, depth=0):
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
