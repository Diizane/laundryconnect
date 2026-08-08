import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:laundryconnect/src/api/api_client.dart';
import 'package:laundryconnect/src/models/provider_documents.dart';
import 'package:laundryconnect/src/models/search.dart';
import 'package:laundryconnect/src/screens/drawing_screen.dart';
import 'package:laundryconnect/src/screens/drawings_list_screen.dart';

import 'fakes.dart';

SearchResult _allianceResult() => const SearchResult(
  providerId: 'alliance',
  sourceReference: 'als-model-430362',
  resultType: 'model',
  dataOrigin: 'live',
  title: 'IAY135J',
  model: 'IAY135J',
  metadata: {'manual_id': '16774', 'model_id': '430362'},
);

Widget _list(FakeProviderDocumentsApi api) => MaterialApp(
  home: DrawingsListScreen(result: _allianceResult(), api: api),
);

Widget _drawing(FakeProviderDocumentsApi api) => MaterialApp(
  home: DrawingScreen(
    title: 'Drive',
    providerId: 'alliance',
    token: 'token-drive',
    api: api,
  ),
);

void main() {
  group('drawing models', () {
    test('parses a drawing list entry', () {
      final summary = DrawingSummary.fromJson(const {
        'token': 'gAAAAA-opaque',
        'title': 'Drive',
        'drawing_id': '548226',
      });
      expect(summary.title, 'Drive');
      expect(summary.drawingId, '548226');
    });

    test('parses a drawing with its parts', () {
      final drawing = DrawingDetail.fromJson(const {
        'svg': '<svg width="7.74in"></svg>',
        'parts': [
          {
            'reference': '8',
            'part_number': 'SP533157',
            'description': 'Belt',
            'comments': null,
          },
        ],
      });
      expect(drawing.hasDiagram, isTrue);
      expect(drawing.parts.single.partNumber, 'SP533157');
    });

    test('parses callouts and their coordinate space', () {
      final drawing = DrawingDetail.fromJson(const {
        'svg': '<svg viewBox="0 0 557.49 699.41"></svg>',
        'view_box': [0, 0, 557.49, 699.41],
        'callouts': [
          {'reference': '8', 'x': 68.58, 'y': 583.38, 'radius': 9.41},
        ],
        'parts': [
          {'reference': '8', 'part_number': 'SP533157', 'description': 'Belt'},
        ],
      });
      expect(drawing.isInteractive, isTrue);
      expect(drawing.callouts.single.x, closeTo(68.58, 0.001));
      expect(drawing.partFor('8')?.partNumber, 'SP533157');
      expect(drawing.partFor('99'), isNull);
    });

    test(
      'a drawing whose export does not label callouts is not interactive',
      () {
        // One of the provider's export pipelines draws callouts anonymously.
        // Those drawings stay viewable and searchable, just not tappable.
        final drawing = DrawingDetail.fromJson(const {
          'svg': '<svg viewBox="0 0 100 100"></svg>',
          'view_box': [0, 0, 100, 100],
          'callouts': <Map<String, dynamic>>[],
          'parts': [
            {
              'reference': '8',
              'part_number': 'SP533157',
              'description': 'Belt',
            },
          ],
        });
        expect(drawing.hasDiagram, isTrue);
        expect(drawing.isInteractive, isFalse);
      },
    );

    test('callouts without a coordinate space are not interactive', () {
      final drawing = DrawingDetail.fromJson(const {
        'svg': '<svg></svg>',
        'callouts': [
          {'reference': '8', 'x': 1.0, 'y': 2.0, 'radius': 3.0},
        ],
      });
      expect(drawing.isInteractive, isFalse);
    });

    test('a drawing without a diagram is reported, not crashed on', () {
      final drawing = DrawingDetail.fromJson(const {'svg': '', 'parts': []});
      expect(drawing.hasDiagram, isFalse);
    });

    group('part matching', () {
      const belt = DrawingPart(
        reference: '8',
        partNumber: 'SP533157',
        description: 'Belt',
      );

      test('matches on description, part number and callout', () {
        expect(belt.matches('belt'), isTrue);
        expect(belt.matches('SP5331'), isTrue);
        expect(belt.matches('8'), isTrue);
      });

      test('is case insensitive and ignores surrounding space', () {
        expect(belt.matches('  BELT '), isTrue);
      });

      test('an empty query matches everything', () {
        expect(belt.matches('   '), isTrue);
      });

      test('does not match unrelated text', () {
        expect(belt.matches('thermostat'), isFalse);
      });

      test('callout matching is exact, not substring', () {
        // '8' must not match reference '18' — a technician reading a
        // callout off the diagram needs the right row.
        const eighteen = DrawingPart(
          reference: '18',
          partNumber: 'X',
          description: 'Bracket',
        );
        expect(eighteen.matches('8'), isFalse);
      });
    });
  });

  group('drawings list screen', () {
    testWidgets('lists drawings for the machine', (tester) async {
      final api = FakeProviderDocumentsApi();
      await tester.pumpWidget(_list(api));
      await tester.pumpAndSettle();

      expect(find.text('Drive'), findsOneWidget);
      expect(find.text('Frame'), findsOneWidget);
      expect(api.drawingListCalls, ['16774:430362']);
    });

    testWidgets('filters by name', (tester) async {
      await tester.pumpWidget(_list(FakeProviderDocumentsApi()));
      await tester.pumpAndSettle();

      await tester.enterText(find.byKey(const Key('drawings-filter')), 'driv');
      await tester.pumpAndSettle();

      expect(find.text('Drive'), findsOneWidget);
      expect(find.text('Frame'), findsNothing);
    });

    testWidgets('empty list says so', (tester) async {
      final api = FakeProviderDocumentsApi(drawingsHandler: (_, _) async => []);
      await tester.pumpWidget(_list(api));
      await tester.pumpAndSettle();

      expect(
        find.text('No assembly drawings listed for this machine.'),
        findsOneWidget,
      );
    });

    testWidgets('failure offers retry', (tester) async {
      var calls = 0;
      final api = FakeProviderDocumentsApi(
        drawingsHandler: (_, _) async {
          calls += 1;
          if (calls == 1) {
            throw const ApiException(
              'Cannot reach the server. Check your connection.',
              kind: ApiErrorKind.network,
            );
          }
          return const [DrawingSummary(token: 'token-drive', title: 'Drive')];
        },
      );
      await tester.pumpWidget(_list(api));
      await tester.pumpAndSettle();
      expect(find.textContaining('Cannot reach the server'), findsOneWidget);

      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.text('Drive'), findsOneWidget);
    });
  });

  group('drawing screen', () {
    testWidgets('shows the parts list with callout numbers', (tester) async {
      final api = FakeProviderDocumentsApi();
      await tester.pumpWidget(_drawing(api));
      await tester.pumpAndSettle();

      expect(find.text('Belt'), findsOneWidget);
      expect(find.text('SP533157'), findsOneWidget);
      // Callout numbers are shown so a number read off the diagram can be
      // found in the list.
      expect(find.text('8'), findsOneWidget);
      expect(api.drawingCalls, ['token-drive']);
    });

    testWidgets('filters parts by description or number', (tester) async {
      await tester.pumpWidget(_drawing(FakeProviderDocumentsApi()));
      await tester.pumpAndSettle();

      await tester.enterText(find.byKey(const Key('parts-filter')), 'belt');
      await tester.pumpAndSettle();

      expect(find.text('Belt'), findsOneWidget);
      expect(find.text('Burner'), findsNothing);
    });

    testWidgets('a drawing without a diagram still shows its parts', (
      tester,
    ) async {
      final api = FakeProviderDocumentsApi(
        drawingHandler: (_, _) async => sampleDrawing(svg: ''),
      );
      await tester.pumpWidget(_drawing(api));
      await tester.pumpAndSettle();

      expect(
        find.text('No diagram available for this drawing.'),
        findsOneWidget,
      );
      expect(find.text('Belt'), findsOneWidget);
    });

    testWidgets('tapping a callout names its part', (tester) async {
      await tester.pumpWidget(_drawing(FakeProviderDocumentsApi()));
      await tester.pumpAndSettle();

      await tester.tap(find.bySemanticsLabel('Callout 8'));
      await tester.pumpAndSettle();

      // The part number is what a technician orders, so it is the headline.
      expect(find.text('SP533157'), findsWidgets);
      expect(find.text('Belt'), findsWidgets);
    });

    testWidgets('a tap target sits over each labelled callout', (tester) async {
      await tester.pumpWidget(_drawing(FakeProviderDocumentsApi()));
      await tester.pumpAndSettle();

      expect(find.bySemanticsLabel('Callout 7'), findsOneWidget);
      expect(find.bySemanticsLabel('Callout 8'), findsOneWidget);
    });

    testWidgets('an unlabelled export offers no tap targets and says nothing '
        'about tapping', (tester) async {
      final api = FakeProviderDocumentsApi(
        drawingHandler: (_, _) async => sampleDrawing(callouts: const []),
      );
      await tester.pumpWidget(_drawing(api));
      await tester.pumpAndSettle();

      expect(find.bySemanticsLabel('Callout 8'), findsNothing);
      expect(find.textContaining('Tap a number'), findsNothing);
      // Still fully usable: the diagram and the searchable list remain.
      expect(find.text('Belt'), findsOneWidget);
    });

    testWidgets('a callout with no matching part does not open a sheet', (
      tester,
    ) async {
      // The backend drops these, but a client that trusted them would show
      // an empty sheet instead of an answer.
      final api = FakeProviderDocumentsApi(
        drawingHandler: (_, _) async => sampleDrawing(
          callouts: const [
            DrawingCallout(reference: '99', x: 20, y: 20, radius: 9),
          ],
        ),
      );
      await tester.pumpWidget(_drawing(api));
      await tester.pumpAndSettle();

      await tester.tap(find.bySemanticsLabel('Callout 99'));
      await tester.pumpAndSettle();

      expect(find.byType(BottomSheet), findsNothing);
    });

    testWidgets('tapping a part row marks it selected', (tester) async {
      await tester.pumpWidget(_drawing(FakeProviderDocumentsApi()));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Belt'));
      await tester.pumpAndSettle();

      final tile = tester.widget<ListTile>(
        find.ancestor(of: find.text('Belt'), matching: find.byType(ListTile)),
      );
      expect(tile.selected, isTrue);
    });
  });
}
