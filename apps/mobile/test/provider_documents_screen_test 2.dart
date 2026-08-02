import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:laundryconnect/src/api/api_client.dart';
import 'package:laundryconnect/src/models/provider_documents.dart';
import 'package:laundryconnect/src/models/search.dart';
import 'package:laundryconnect/src/screens/provider_documents_screen.dart';

import 'fakes.dart';

SearchResult _allianceResult({Map<String, String>? metadata}) => SearchResult(
  providerId: 'alliance',
  sourceReference: 'als-model-395125',
  resultType: 'model',
  dataOrigin: 'live',
  title: 'BA120N',
  model: 'BA120N',
  metadata: metadata ?? const {'manual_id': '16677', 'model_id': '395125'},
);

Widget _screen(
  FakeProviderDocumentsApi api, {
  SearchResult? result,
  PdfOpener? openPdf,
}) => MaterialApp(
  home: ProviderDocumentsScreen(
    result: result ?? _allianceResult(),
    api: api,
    openPdf:
        openPdf ??
        (BuildContext context, String title, Uint8List bytes) async {},
  ),
);

void main() {
  group('model parsing', () {
    test('provider document parses backend json', () {
      final doc = ProviderDocument.fromJson(const {
        'token': 'gAAAAA-opaque',
        'title': 'D0568 — Technical Mnl',
        'document_type': 'Technical Mnl',
        'part_number': 'D0568',
        'comment': 'Date 9/99',
        'languages': ['English'],
        'category': 'Production',
        'filename': 'D0568.pdf',
        'available': true,
        'data_origin': 'live',
      });
      expect(doc.token, 'gAAAAA-opaque');
      expect(doc.isDownloadable, isTrue);
      expect(doc.languages, ['English']);
    });

    test('unavailable document without token is not downloadable', () {
      final doc = ProviderDocument.fromJson(const {
        'token': null,
        'title': 'D0300',
        'available': false,
        'data_origin': 'live',
      });
      expect(doc.isDownloadable, isFalse);
    });

    test('alliance documentRef built from search metadata', () {
      expect(_allianceResult().documentRef, '16677:395125');
    });

    test('alliance result without metadata has no documentRef', () {
      expect(_allianceResult(metadata: const {}).documentRef, isNull);
    });

    test('mock results use their source reference as ref', () {
      const result = SearchResult(
        providerId: 'mock',
        sourceReference: 'mock-doc-sc60-service',
        resultType: 'document',
        dataOrigin: 'mock',
        title: 'SC60 Service Manual (sample)',
      );
      expect(result.documentRef, 'mock-doc-sc60-service');
    });
  });

  group('document list', () {
    testWidgets('lists documents with metadata badges', (tester) async {
      await tester.pumpWidget(_screen(FakeProviderDocumentsApi()));
      await tester.pumpAndSettle();

      expect(find.text('D0568 — Technical Mnl'), findsOneWidget);
      expect(find.text('Technical Mnl'), findsOneWidget);
      expect(find.text('D0568'), findsOneWidget);
      expect(find.text('Production'), findsOneWidget);
      expect(find.text('English'), findsNWidgets(2));
      expect(find.text('Date 9/99'), findsOneWidget);
    });

    testWidgets('unavailable document is disabled and labelled', (
      tester,
    ) async {
      final api = FakeProviderDocumentsApi();
      await tester.pumpWidget(_screen(api));
      await tester.pumpAndSettle();

      expect(find.text('not downloadable'), findsOneWidget);
      final tile = tester.widget<ListTile>(
        find.ancestor(
          of: find.text('D0300 — Legacy Bulletin'),
          matching: find.byType(ListTile),
        ),
      );
      expect(tile.enabled, isFalse);

      await tester.tap(find.text('D0300 — Legacy Bulletin'));
      await tester.pumpAndSettle();
      expect(api.downloadCalls, isEmpty);
    });

    testWidgets('empty discovery shows honest message', (tester) async {
      final api = FakeProviderDocumentsApi(
        discoverHandler: (_, _) async =>
            const DocumentDiscovery(providerId: 'alliance', documents: []),
      );
      await tester.pumpWidget(_screen(api));
      await tester.pumpAndSettle();

      expect(
        find.text('No documents listed for this machine.'),
        findsOneWidget,
      );
    });

    testWidgets('discovery failure shows message and retry works', (
      tester,
    ) async {
      var calls = 0;
      final api = FakeProviderDocumentsApi(
        discoverHandler: (_, _) async {
          calls += 1;
          if (calls == 1) {
            throw const ApiException(
              'The provider could not complete that request.',
              kind: ApiErrorKind.providerFailure,
            );
          }
          return sampleDiscovery();
        },
      );
      await tester.pumpWidget(_screen(api));
      await tester.pumpAndSettle();

      expect(
        find.text('The provider could not complete that request.'),
        findsOneWidget,
      );

      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.text('D0568 — Technical Mnl'), findsOneWidget);
    });

    testWidgets('reauthentication failure shows operator message', (
      tester,
    ) async {
      final api = FakeProviderDocumentsApi(
        discoverHandler: (_, _) async {
          throw const ApiException(
            'The Alliance session needs to be signed in again by an '
            'operator. Try again once that is done.',
            kind: ApiErrorKind.reauthenticationRequired,
          );
        },
      );
      await tester.pumpWidget(_screen(api));
      await tester.pumpAndSettle();

      expect(find.textContaining('signed in again by an'), findsOneWidget);
      expect(find.byIcon(Icons.lock_outline), findsOneWidget);
    });
  });

  group('download and open', () {
    testWidgets('tapping a document downloads and opens the PDF', (
      tester,
    ) async {
      final api = FakeProviderDocumentsApi();
      final opened = <String>[];
      await tester.pumpWidget(
        _screen(
          api,
          openPdf: (_, title, bytes) async {
            opened.add('$title:${bytes.length}');
          },
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('D0568 — Technical Mnl'));
      await tester.pumpAndSettle();

      expect(api.downloadCalls, ['token-technical']);
      expect(opened, ['D0568 — Technical Mnl:${samplePdfBytes.length}']);
    });

    testWidgets('expired token triggers one rediscovery then retries', (
      tester,
    ) async {
      final api = FakeProviderDocumentsApi();
      api.discoverHandler = (_, _) async => sampleDiscovery(
        tokenSuffix: api.discoverCalls.length > 1 ? '-fresh' : '',
      );
      api.downloadHandler = (_, token) async {
        if (token == 'token-technical') {
          throw const ApiException('Not found.', kind: ApiErrorKind.notFound);
        }
        return samplePdfBytes;
      };
      final opened = <String>[];
      await tester.pumpWidget(
        _screen(api, openPdf: (_, title, bytes) async => opened.add(title)),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('D0568 — Technical Mnl'));
      await tester.pumpAndSettle();

      // First attempt with the stale token, rediscovery, then the fresh one.
      expect(api.downloadCalls, ['token-technical', 'token-technical-fresh']);
      expect(api.discoverCalls.length, 2);
      expect(opened, ['D0568 — Technical Mnl']);
      // Token mechanics never surface to the technician.
      expect(find.textContaining('token'), findsNothing);
    });

    testWidgets('download provider failure surfaces safe message', (
      tester,
    ) async {
      final api = FakeProviderDocumentsApi(
        downloadHandler: (_, _) async {
          throw const ApiException(
            'Provider returned invalid document content.',
            kind: ApiErrorKind.providerFailure,
          );
        },
      );
      await tester.pumpWidget(_screen(api));
      await tester.pumpAndSettle();

      await tester.tap(find.text('D0568 — Technical Mnl'));
      await tester.pumpAndSettle();

      expect(
        find.text('Provider returned invalid document content.'),
        findsOneWidget,
      );
    });
  });
}
