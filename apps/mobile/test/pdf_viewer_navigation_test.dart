import 'package:flutter_test/flutter_test.dart';
import 'package:laundryconnect/src/api/api_client.dart';
import 'package:laundryconnect/src/models/provider_documents.dart';

import 'fakes.dart';

/// The viewer's search and contents behaviour, exercised through the API
/// contract rather than the PDF renderer (which needs a real platform).
void main() {
  group('document contents model', () {
    test('parses backend contents payload', () {
      final contents = DocumentContents.fromJson(const {
        'page_count': 82,
        'searchable': true,
        'searchable_pages': 81,
        'contents': [
          {'title': 'Cover', 'page_number': 1, 'depth': 0},
          {'title': 'Drum Drive', 'page_number': 47, 'depth': 1},
        ],
      });
      expect(contents.pageCount, 82);
      expect(contents.searchable, isTrue);
      expect(contents.hasContents, isTrue);
      expect(contents.contents[1].pageNumber, 47);
      expect(contents.contents[1].depth, 1);
    });

    test('an unsearchable document is reported, not silently empty', () {
      // Real manuals (e.g. Alliance D0167) embed fonts without character
      // maps, so there is no text to search. The UI must say so.
      final contents = DocumentContents.fromJson(const {
        'page_count': 35,
        'searchable': false,
        'searchable_pages': 0,
        'contents': [],
      });
      expect(contents.searchable, isFalse);
      expect(contents.hasContents, isFalse);
    });

    test('missing contents list parses as empty rather than failing', () {
      final contents = DocumentContents.fromJson(const {
        'page_count': 10,
        'searchable': true,
        'searchable_pages': 10,
      });
      expect(contents.contents, isEmpty);
    });
  });

  group('document search model', () {
    test('parses page-cited hits', () {
      final results = DocumentSearchResults.fromJson(const {
        'query': 'belt',
        'searchable': true,
        'total_hits': 2,
        'hits': [
          {'page_number': 47, 'snippet': '…Drum Drive - DR20…'},
          {'page_number': 49, 'snippet': '…Drum Drive - DR30…'},
        ],
      });
      expect(results.query, 'belt');
      expect(results.hits.map((h) => h.pageNumber), [47, 49]);
    });

    test('distinguishes no-matches from not-searchable', () {
      final noMatches = DocumentSearchResults.fromJson(const {
        'query': 'hydraulic',
        'searchable': true,
        'total_hits': 0,
        'hits': [],
      });
      final notSearchable = DocumentSearchResults.fromJson(const {
        'query': 'hydraulic',
        'searchable': false,
        'total_hits': 0,
        'hits': [],
      });
      expect(noMatches.searchable, isTrue);
      expect(notSearchable.searchable, isFalse);
    });
  });

  group('api client contract', () {
    testWidgets('contents and search reach the backend with the token', (
      tester,
    ) async {
      final api = FakeProviderDocumentsApi();
      await api.documentContents('alliance', 'token-technical');
      await api.searchWithinDocument('alliance', 'token-technical', 'belt');

      expect(api.contentsCalls, ['token-technical']);
      expect(api.searchCalls, ['belt']);
    });

    testWidgets('search failures surface a safe message', (tester) async {
      final api = FakeProviderDocumentsApi(
        searchHandler: (_, _, _) async {
          throw const ApiException(
            'The provider could not complete that request.',
            kind: ApiErrorKind.providerFailure,
          );
        },
      );
      await expectLater(
        api.searchWithinDocument('alliance', 't', 'belt'),
        throwsA(isA<ApiException>()),
      );
    });
  });
}
