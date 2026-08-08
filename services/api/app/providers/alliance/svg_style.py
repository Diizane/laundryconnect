"""Inline an SVG's own stylesheet onto its elements.

One of the provider's CAD export pipelines styles every shape with a CSS
class and puts the rules in a `<style>` block inside the SVG:

    <style type="text/css">.x1342269031_st7{fill:#FFFFFF;stroke:#000000;}</style>
    …
    <path class="x1342269031_st7" d="…"/>

The app renders SVG with flutter_svg, whose compiler lists `<style/>` among
its unhandled elements: the rules are dropped, every shape falls back to a
default black fill, and the drawing arrives as a black silhouette. Field
report, 2026-08-08: Water Inlet System and Rear Panel showed black; Frame,
whose export writes inline `style` attributes instead, was fine.

Rather than hope a renderer grows CSS support, the declarations are copied
onto the elements here, where it can be tested. Only simple class selectors
are applied — that is all this provider emits (measured: 24 rules on Water
Inlet System, 18 on Rear Panel, every one a bare `.class`). Anything more
complicated is left alone, and the `<style>` block is always kept, so a
renderer that does understand CSS sees exactly what it saw before.
"""

import logging
import re

logger = logging.getLogger(__name__)

_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.S | re.I)
_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_SIMPLE_CLASS = re.compile(r"^\.([\w-]+)$")
# An element open tag carrying a class attribute.
_CLASSED_ELEMENT = re.compile(r'<[\w:-]+\b[^>]*\bclass\s*=\s*"[^"]*"[^>]*>', re.I)
_CLASS_ATTR = re.compile(r'\bclass\s*=\s*"([^"]*)"', re.I)
_STYLE_ATTR = re.compile(r'\bstyle\s*=\s*"([^"]*)"', re.I)


def parse_rules(stylesheet: str) -> tuple[dict[str, str], int]:
    """Declarations per class name, plus the count of selectors skipped.

    Rules are merged in document order, so a later rule for the same class
    overrides an earlier one — the cascade for equally specific selectors.
    """
    rules: dict[str, str] = {}
    skipped = 0
    for selector_group, declarations in _RULE.findall(_COMMENT.sub("", stylesheet)):
        body = declarations.strip().strip(";").strip()
        if not body:
            continue
        for selector in selector_group.split(","):
            match = _SIMPLE_CLASS.match(selector.strip())
            if match is None:
                skipped += 1
                continue
            name = match.group(1)
            rules[name] = f"{rules[name]};{body}" if name in rules else body
    return rules, skipped


def _apply(tag: str, rules: dict[str, str]) -> str:
    classes = _CLASS_ATTR.search(tag)
    if classes is None:
        return tag
    declarations = [rules[name] for name in classes.group(1).split() if name in rules]
    if not declarations:
        return tag

    inline = _STYLE_ATTR.search(tag)
    if inline is not None:
        # An inline style attribute outranks a class rule, so it goes last.
        own = inline.group(1).strip().strip(";").strip()
        if own:
            declarations.append(own)
        merged = ";".join(declarations)
        return tag[: inline.start()] + f'style="{merged}"' + tag[inline.end() :]

    merged = ";".join(declarations)
    closing = "/>" if tag.endswith("/>") else ">"
    return f'{tag[: -len(closing)].rstrip()} style="{merged}"{closing}'


def inline_stylesheet(svg: str) -> str:
    """Copy the SVG's class rules onto the elements that reference them.

    The `<style>` block is left in place and `class` attributes are kept;
    this only adds what a CSS-less renderer would otherwise miss.
    """
    if not svg or "<style" not in svg.lower():
        return svg
    rules: dict[str, str] = {}
    skipped = 0
    for block in _STYLE_BLOCK.findall(svg):
        block_rules, block_skipped = parse_rules(block)
        rules.update(block_rules)
        skipped += block_skipped
    if not rules:
        return svg
    if skipped:
        # Left to the renderer; noted because it means this drawing may still
        # rely on CSS the app cannot apply.
        logger.info(
            "alliance drawing: stylesheet has selectors that were not inlined",
            extra={"skipped_selectors": skipped},
        )
    return _CLASSED_ELEMENT.sub(lambda m: _apply(m.group(0), rules), svg)
