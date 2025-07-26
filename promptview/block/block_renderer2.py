from promptview.block.block7 import  Block, BlockContext, BlockList
from promptview.block.style2 import StyleManager
from promptview.block.renderers import (
    AsteriskListRenderer,
    BulletListRenderer,
    CheckboxListRenderer,
    DashListRenderer,
    PlusListRenderer,
    RenderContext,
    ContentRenderer,
    RendererRegistry,
    MarkdownHeaderRenderer,
    # YamlRenderer,
    # JsonRenderer,
    XmlTitleRenderer,
    NumberedListRenderer,
    # BulletedListRenderer
)

# initialize global registries
style_manager = StyleManager()


style_manager.add_style(["markdown-title", "md"], {"title-format": "markdown-title"})

style_manager.add_style(["list-num", "li1"], {"list-format": "numbered-list"})
style_manager.add_style(["list-bullet", "li•"], {"list-format": "bullet-list"})
style_manager.add_style(["list-dash", "li-"], {"list-format": "dash-list"})
style_manager.add_style(["list-plus", "li+"], {"list-format": "plus-list"})
style_manager.add_style(["list-asterisk", "li*"], {"list-format": "asterisk-list"})

style_manager.add_style(["list-checkbox", "li[]"], {"list-format": "checkbox-list"})




style_manager.add_style(["row", "list-row"], {"row-format": "row-list"})



style_manager.add_style(["xml"], {"title-format": "xml-title"})

renderer_registry = RendererRegistry()

# register default renderers
renderer_registry.register("markdown-title", MarkdownHeaderRenderer())
renderer_registry.register("xml-title", XmlTitleRenderer())


renderer_registry.register("numbered-list", NumberedListRenderer())
renderer_registry.register("bullet-list", BulletListRenderer())
renderer_registry.register("dash-list", DashListRenderer())
renderer_registry.register("plus-list", PlusListRenderer())
renderer_registry.register("checkbox-list", CheckboxListRenderer())
renderer_registry.register("asterisk-list", AsteriskListRenderer())


renderer_registry.register("row-list", ContentRenderer())


default_renderer = ContentRenderer()



def combine_content(left: str, right: str, sep: str):
    if left and right:
        return left + sep + right
    elif left:
        return left
    elif right:
        return right


def render(target, index=0, depth=0, style=None, parent_ctx: RenderContext | None = None):
    if style is None:
        style = style_manager.resolve(target)
    ctx = RenderContext(target, style, index, depth, parent_ctx)
    if isinstance(target, BlockContext):
        return render_context(target, ctx)
    elif isinstance(target, BlockList):
        return render_item_list(target, ctx)
    elif isinstance(target, Block):
        return render_block(target, ctx)
    else:
        raise ValueError(f"Invalid block type: {type(target)}")
    
    
def render_block(block: Block, ctx: RenderContext):
    fmt = ctx.style.get("block-format")
    renderer = renderer_registry.get(fmt) if fmt else default_renderer    
    content = renderer.try_render(ctx, block.content)
    return content

def render_row(block_list: BlockList, ctx: RenderContext):
    fmt = ctx.style.get("row-format")
    renderer = renderer_registry.get(fmt) if fmt else default_renderer
    item_content = [render(item, index=index, depth=ctx.depth, style=ctx.style, parent_ctx=ctx) for index, item in enumerate(block_list)]
    content = renderer.try_render_list(ctx, item_content)
    return content
    
def render_item_list(block_list: BlockList, ctx: RenderContext):
    fmt = ctx.style.get("list-format")
    renderer = renderer_registry.get(fmt) if fmt else default_renderer    
    item_content = [render(item, index=index, depth=ctx.depth, style=ctx.style, parent_ctx=ctx) for index, item in enumerate(block_list)]
    content = renderer.try_render_list(ctx, item_content)
    return content
    


def render_context(block: BlockContext, ctx: RenderContext):
    
    #! render title content
    title_fmt = ctx.style.get("title-format") 
    title_content = render_row(block.root, ctx) if not ctx.is_wrapper else ""
    if title_content and block.wrap:
        title_content = block.wrap[0] + title_content + block.wrap[1]
    
    #! render children
    # children_content = render_item_list(block.children, ctx)
    child_depth = ctx.depth + 1 if not ctx.is_wrapper else ctx.depth    
    children_content = render(block.children, ctx.index, child_depth, None, ctx)
    if block.vwrap and children_content:
        children_content = block.vwrap[0] + children_content + block.vwrap[1]
    
    #! render title with children content
    title_renderer = renderer_registry.get(title_fmt) if title_fmt else default_renderer
    content = title_renderer.try_render(ctx, title_content, children_content)
    return content
        
    # return combine_content(title_content, children_content, "\n")
  
# def render_context(block: BlockContext, ctx: RenderContext):
#     title_fmt = ctx.style.get("title-format")
#     list_fmt = ctx.style.get("list-format")
#     root_content = render_list(block.root, ctx)
#     renderer = renderer_registry.get(title_fmt) if title_fmt else default_renderer    
#     root_content = renderer.render(ctx, root_content, root_content)        
#     children_content = render_list(block.children, ctx)
    
#     if block.wrap:
#         root_content = block.wrap[0] + root_content + block.wrap[1]
#     if block.vwrap and children_content:
#         children_content = block.vwrap[0] + children_content + block.vwrap[1]
        
#     return combine_content(root_content, children_content, "\n")
    





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
