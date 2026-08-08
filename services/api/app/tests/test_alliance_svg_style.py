"""Inlining an assembly drawing's own stylesheet.

flutter_svg does not apply CSS — `<style/>` is unhandled by its compiler —
so a drawing styled entirely by class arrives as a black silhouette. These
pin the declarations onto the elements instead. The markup shapes are taken
from the real Water Inlet System and Rear Panel drawings.
"""

from app.providers.alliance.svg_style import inline_stylesheet, parse_rules

STYLESHEET = (
    '<style type="text/css">\n'
    "\t.x1342269031_st0{opacity:0;fill:none;}\n"
    "\t.x1342269031_st7{fill:#FFFFFF;stroke:#000000;stroke-width:0.25px;}\n"
    "</style>"
)


def svg(body: str, stylesheet: str = STYLESHEET) -> str:
    return f'<svg viewBox="0 0 100 100">{stylesheet}{body}</svg>'


def _body(svg_text: str) -> str:
    """Everything after the stylesheet — the rules themselves mention the
    same declarations, so assertions must look past them."""
    return svg_text.split("</style>")[-1]


class TestParseRules:
    def test_reads_simple_class_rules(self) -> None:
        rules, skipped = parse_rules(".a{fill:red;}.b{stroke:blue}")
        assert rules == {"a": "fill:red", "b": "stroke:blue"}
        assert skipped == 0

    def test_a_grouped_selector_applies_to_each_class(self) -> None:
        rules, _ = parse_rules(".a,.b{fill:red;}")
        assert rules == {"a": "fill:red", "b": "fill:red"}

    def test_a_later_rule_is_appended_so_it_wins(self) -> None:
        rules, _ = parse_rules(".a{fill:red;}.a{fill:blue;}")
        assert rules["a"] == "fill:red;fill:blue"

    def test_comments_are_ignored(self) -> None:
        rules, _ = parse_rules("/* header .x{fill:none} */ .a{fill:red;}")
        assert rules == {"a": "fill:red"}

    def test_selectors_that_are_not_plain_classes_are_counted_not_applied(self) -> None:
        rules, skipped = parse_rules("#id{fill:red;} path{fill:blue;} .a .b{fill:green;}")
        assert rules == {}
        assert skipped == 3


class TestInlining:
    def test_a_class_becomes_a_style_attribute(self) -> None:
        result = inline_stylesheet(svg('<path class="x1342269031_st7" d="M1 1"/>'))
        assert 'style="fill:#FFFFFF;stroke:#000000;stroke-width:0.25px"' in result

    def test_several_classes_are_merged(self) -> None:
        result = inline_stylesheet(svg('<path class="x1342269031_st0 x1342269031_st7" d="M1 1"/>'))
        assert 'style="opacity:0;fill:none;fill:#FFFFFF;stroke:#000000;stroke-width:0.25px"' in (
            result
        )

    def test_an_existing_inline_style_still_wins(self) -> None:
        """Order matters: the element's own style is written last, so a
        renderer resolving left-to-right keeps the author's override."""
        result = inline_stylesheet(
            svg('<path class="x1342269031_st7" style="fill:#00FF00" d="M1 1"/>')
        )
        assert 'style="fill:#FFFFFF;stroke:#000000;stroke-width:0.25px;fill:#00FF00"' in result

    def test_the_stylesheet_and_classes_are_kept(self) -> None:
        """A renderer that does understand CSS must see what it saw before."""
        result = inline_stylesheet(svg('<path class="x1342269031_st7" d="M1 1"/>'))
        assert "<style" in result
        assert 'class="x1342269031_st7"' in result

    def test_an_unknown_class_is_left_alone(self) -> None:
        result = inline_stylesheet(svg('<path class="not-in-sheet" d="M1 1"/>'))
        assert "style=" not in _body(result)

    def test_elements_without_a_class_are_untouched(self) -> None:
        result = inline_stylesheet(svg('<path d="M1 1"/>'))
        assert "style=" not in _body(result)

    def test_a_drawing_with_no_stylesheet_is_returned_unchanged(self) -> None:
        original = '<svg viewBox="0 0 1 1"><path style="fill:#fff" d="M1 1"/></svg>'
        assert inline_stylesheet(original) == original

    def test_empty_input_is_not_an_error(self) -> None:
        assert inline_stylesheet("") == ""

    def test_self_closing_and_open_tags_both_work(self) -> None:
        result = inline_stylesheet(
            svg('<g class="x1342269031_st0"><path class="x1342269031_st0" d="M1 1"/></g>')
        )
        assert result.count('style="opacity:0;fill:none"') == 2

    def test_every_styled_element_ends_up_with_a_style(self) -> None:
        """The property that matters: after inlining, nothing that a rule
        applies to is left relying on CSS."""
        body = "".join(f'<path class="x1342269031_st7" d="M{i} {i}"/>' for i in range(50))
        result = inline_stylesheet(svg(body))
        assert _body(result).count("stroke-width:0.25px") == 50
