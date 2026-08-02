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

  group('grouping and ordering', () {
    test('documents group by type, most field-useful first', () {
      // Mirrors a real BA120N response: the provider lists compliance
      // paperwork first, which buries the manuals a technician wants.
      ProviderDocument doc(String type, String part) => ProviderDocument(
        token: 'token-$part',
        title: '$part — $type',
        documentType: type,
        partNumber: part,
        available: true,
        dataOrigin: 'live',
      );
      final discovery = DocumentDiscovery(
        providerId: 'alliance',
        documents: [
          doc('Declaration of Conformity', '70558201-2021'),
          doc('Declaration of Conformity', '70558201-2022'),
          doc('Installation Operation Maintenance Mnl', 'D0167'),
          doc('Parts Mnl', 'D0287'),
          doc('Technical Mnl', 'D0568'),
        ],
      );

      final groups = discovery.groups;
      expect(groups.map((g) => g.documentType), [
        'Technical Mnl',
        'Parts Mnl',
        'Installation Operation Maintenance Mnl',
        'Declaration of Conformity', // compliance paperwork sinks to last
      ]);
      expect(groups.first.documents.single.partNumber, 'D0568');
      expect(groups.last.documents.length, 2);
    });

    test('missing document type falls into an Other group', () {
      const discovery = DocumentDiscovery(
        providerId: 'alliance',
        documents: [
          ProviderDocument(
            token: 't',
            title: 'D0999.pdf',
            available: true,
            dataOrigin: 'live',
          ),
        ],
      );
      expect(discovery.groups.single.documentType, 'Other');
    });

    test('non-English documents are hidden, multi-language ones kept', () {
      ProviderDocument doc(String part, List<String> languages) =>
          ProviderDocument(
            token: 'token-$part',
            title: part,
            documentType: 'Technical Mnl',
            partNumber: part,
            languages: languages,
            available: true,
            dataOrigin: 'live',
          );
      final discovery = DocumentDiscovery(
        providerId: 'alliance',
        documents: [
          doc('english-only', ['English']),
          // Multi-language file that includes English — usable, so kept.
          doc('multi', ['English', 'česky', 'Dansk']),
          doc('german-only', ['Deutsch']),
          doc('czech-only', ['česky', 'Polski']),
          doc('unlisted', const []), // unclassified: shown, never hidden
        ],
      );

      expect(discovery.englishDocuments.map((d) => d.partNumber), [
        'english-only',
        'multi',
        'unlisted',
      ]);
      expect(discovery.hiddenNonEnglishCount, 2);
    });

    test('English matching tolerates provider spelling and case', () {
      for (final language in ['English', 'english', ' EN ', 'English CE']) {
        final doc = ProviderDocument(
          token: 't',
          title: 'x',
          languages: [language],
          available: true,
          dataOrigin: 'live',
        );
        expect(doc.isEnglish, isTrue, reason: language);
      }
    });

    test('groups only contain English documents', () {
      final discovery = DocumentDiscovery(
        providerId: 'alliance',
        documents: [
          const ProviderDocument(
            token: 't1',
            title: 'EN manual',
            documentType: 'Technical Mnl',
            languages: ['English'],
            available: true,
            dataOrigin: 'live',
          ),
          const ProviderDocument(
            token: 't2',
            title: 'DE manual',
            documentType: 'Wiring Diagram',
            languages: ['Deutsch'],
            available: true,
            dataOrigin: 'live',
          ),
        ],
      );
      expect(discovery.groups.map((g) => g.documentType), ['Technical Mnl']);
    });

    test('downloadable count excludes unavailable documents', () {
      final group = sampleDiscovery().groups.firstWhere(
        (g) => g.documentType == 'Bulletin',
      );
      expect(group.documents.length, 1);
      expect(group.downloadableCount, 0);
    });
  });

  group('document list', () {
    testWidgets('shows one collapsible section per document type', (
      tester,
    ) async {
      await tester.pumpWidget(_screen(FakeProviderDocumentsApi()));
      await tester.pumpAndSettle();

      // Both categories visible without scrolling; rows hidden until asked.
      expect(find.text('Technical Mnl'), findsOneWidget);
      expect(find.text('Bulletin'), findsOneWidget);
      expect(find.text('1 document'), findsNWidgets(2));
      expect(find.text('D0568 — Technical Mnl'), findsNothing);
    });

    testWidgets('expanding a section reveals its documents and metadata', (
      tester,
    ) async {
      await tester.pumpWidget(_screen(FakeProviderDocumentsApi()));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Technical Mnl'));
      await tester.pumpAndSettle();

      expect(find.text('D0568 — Technical Mnl'), findsOneWidget);
      expect(find.text('D0568'), findsOneWidget);
      expect(find.text('Production'), findsOneWidget);
      expect(find.text('Date 9/99'), findsOneWidget);
    });

    testWidgets('a single-category machine opens expanded', (tester) async {
      final api = FakeProviderDocumentsApi(
        discoverHandler: (_, _) async => DocumentDiscovery(
          providerId: 'alliance',
          documents: sampleDiscovery().documents
              .where((d) => d.documentType == 'Technical Mnl')
              .toList(),
        ),
      );
      await tester.pumpWidget(_screen(api));
      await tester.pumpAndSettle();

      // Nothing to choose between — no extra tap required.
      expect(find.text('D0568 — Technical Mnl'), findsOneWidget);
    });

    testWidgets('unavailable document is disabled and labelled', (
      tester,
    ) async {
      final api = FakeProviderDocumentsApi();
      await tester.pumpWidget(_screen(api));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Bulletin'));
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

    testWidgets('all-non-English discovery says so distinctly', (tester) async {
      final api = FakeProviderDocumentsApi(
        discoverHandler: (_, _) async => const DocumentDiscovery(
          providerId: 'alliance',
          documents: [
            ProviderDocument(
              token: 't',
              title: 'Betriebsanleitung',
              documentType: 'Technical Mnl',
              languages: ['Deutsch'],
              available: true,
              dataOrigin: 'live',
            ),
          ],
        ),
      );
      await tester.pumpWidget(_screen(api));
      await tester.pumpAndSettle();

      // Distinct from "no documents" — the machine has documents, just none
      // this technician can read.
      expect(
        find.text('No English documents listed for this machine.'),
        findsOneWidget,
      );
    });

    testWidgets('language badge is not shown on rows', (tester) async {
      await tester.pumpWidget(_screen(FakeProviderDocumentsApi()));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Technical Mnl'));
      await tester.pumpAndSettle();

      // Every row is English now, so the badge would be pure repetition.
      expect(find.text('English'), findsNothing);
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
      // Recovered: the grouped list is shown again.
      expect(find.text('Technical Mnl'), findsOneWidget);
      expect(find.text('Bulletin'), findsOneWidget);
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
      await tester.tap(find.text('Technical Mnl'));
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
      await tester.tap(find.text('Technical Mnl'));
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
      await tester.tap(find.text('Technical Mnl'));
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
