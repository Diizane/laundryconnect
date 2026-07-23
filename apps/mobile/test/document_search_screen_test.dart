import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:laundryconnect/src/api/api_client.dart';
import 'package:laundryconnect/src/models/document_search.dart';
import 'package:laundryconnect/src/screens/document_search_screen.dart';
import 'package:laundryconnect/src/theme/app_theme.dart';

import 'fakes.dart';

Future<void> _pump(WidgetTester tester, FakeDocumentsApi api) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: buildAppTheme(),
      home: DocumentSearchScreen(
        document: sampleServiceManual,
        documentsApi: api,
      ),
    ),
  );
}

Future<void> _search(WidgetTester tester, String query) async {
  await tester.enterText(find.byType(TextField), query);
  await tester.tap(find.byKey(const Key('doc-search-button')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('initial state prompts for an in-document search', (
    tester,
  ) async {
    await _pump(tester, FakeDocumentsApi());
    expect(find.textContaining('jump to the right page'), findsOneWidget);
  });

  testWidgets('search shows page-cited hits with snippets', (tester) async {
    await _pump(tester, FakeDocumentsApi());
    await _search(tester, 'EdL');

    expect(find.text('Page 2'), findsOneWidget);
    expect(find.textContaining('door lock error'), findsOneWidget);
  });

  testWidgets('tapping a hit opens the page text with navigation', (
    tester,
  ) async {
    await _pump(tester, FakeDocumentsApi());
    await _search(tester, 'EdL');

    await tester.tap(find.textContaining('door lock error'));
    await tester.pumpAndSettle();

    expect(find.text('Page 2'), findsOneWidget); // app bar
    expect(find.textContaining('SAMPLE PAGE 2'), findsOneWidget);

    await tester.tap(find.byKey(const Key('next-page')));
    await tester.pumpAndSettle();
    expect(find.text('Page 3'), findsOneWidget);
    expect(find.textContaining('SAMPLE PAGE 3'), findsOneWidget);

    await tester.tap(find.byKey(const Key('prev-page')));
    await tester.pumpAndSettle();
    expect(find.text('Page 2'), findsOneWidget);
  });

  testWidgets('no hits shows an honest empty message', (tester) async {
    final api = FakeDocumentsApi(
      searchHandler: (_, query) async =>
          DocumentSearchResult(query: query, totalHits: 0, hits: const []),
    );
    await _pump(tester, api);
    await _search(tester, 'unobtainium');

    expect(find.text('No pages match "unobtainium".'), findsOneWidget);
  });

  testWidgets('search failure shows error with retry', (tester) async {
    var calls = 0;
    final api = FakeDocumentsApi(
      searchHandler: (documentId, query) {
        calls++;
        if (calls == 1) {
          return Future.error(const ApiException('Cannot reach the server.'));
        }
        return FakeDocumentsApi().searchInDocument(documentId, query);
      },
    );
    await _pump(tester, api);
    await _search(tester, 'EdL');

    expect(find.text('Cannot reach the server.'), findsOneWidget);

    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    expect(find.text('Page 2'), findsOneWidget);
  });

  testWidgets('queries shorter than two characters are not sent', (
    tester,
  ) async {
    var searches = 0;
    final api = FakeDocumentsApi(
      searchHandler: (documentId, query) {
        searches++;
        return FakeDocumentsApi().searchInDocument(documentId, query);
      },
    );
    await _pump(tester, api);
    await _search(tester, 'x');

    expect(searches, 0);
    expect(find.textContaining('jump to the right page'), findsOneWidget);
  });
}
