/// Pins what the app's SVG renderer actually does with a stylesheet.
///
/// A field report on 2026-08-08 was that the Water Inlet System and Rear
/// Panel drawings rendered solid black. Those come from a CAD export that
/// styles every shape with a CSS class; flutter_svg's compiler lists
/// `<style/>` among its unhandled elements, so the rules are dropped and
/// shapes fall back to a black fill.
///
/// The fix is in the backend (services/api/.../svg_style.py), which copies
/// the declarations onto the elements. These tests exercise the renderer
/// directly so the assumption behind that fix is verified here rather than
/// taken on trust — and so we find out if flutter_svg ever gains CSS
/// support, at which point the backend transformation could be dropped.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:vector_graphics_compiler/vector_graphics_compiler.dart' as vg;

const _white = 0xFFFFFFFF;
const _black = 0xFF000000;

/// Styled only by a class rule in a `<style>` block — what the provider
/// sends for roughly half its drawings.
const _classStyled = '''
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <style type="text/css">.st7{fill:#FFFFFF;}</style>
  <path class="st7" d="M10,10 L90,10 L90,90 L10,90 Z"/>
</svg>''';

/// The same drawing after the backend inlines its stylesheet.
const _inlined = '''
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <style type="text/css">.st7{fill:#FFFFFF;}</style>
  <path class="st7" style="fill:#FFFFFF" d="M10,10 L90,10 L90,90 L10,90 Z"/>
</svg>''';

Set<int> _fillColours(String svg) {
  // Without the optimizers: those need the native PathOps library, which is
  // not loaded in a plain test run and is irrelevant to how paints resolve.
  final instructions = vg.parseWithoutOptimizers(svg);
  return instructions.paints
      .map((paint) => paint.fill?.color.value)
      .whereType<int>()
      .toSet();
}

void main() {
  group('the renderer and CSS', () {
    test('a class rule is NOT applied — the shape comes out black', () {
      // Not desired behaviour, just true behaviour. If this test starts
      // failing, flutter_svg has learned CSS and svg_style.py can go.
      expect(_fillColours(_classStyled), contains(_black));
      expect(_fillColours(_classStyled), isNot(contains(_white)));
    });

    test('the same declaration inlined IS applied', () {
      expect(_fillColours(_inlined), contains(_white));
    });
  });
}
