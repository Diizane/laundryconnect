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
  });
}
