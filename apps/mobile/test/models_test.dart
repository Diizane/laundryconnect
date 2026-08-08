import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:laundryconnect/src/models/search.dart';

const sampleResponseJson = '''
{
  "query": "SC60",
  "requested_query_type": "auto",
  "detected_query_type": "model",
  "total_results": 2,
  "groups": [
    {
      "manufacturer": "Alliance Laundry Systems",
      "brand": "Speed Queen",
      "model": "SC60",
      "results": [
        {
          "provider_id": "mock",
          "source_reference": "mock-doc-sc60-service",
          "result_type": "document",
          "data_origin": "mock",
          "title": "SC60 Service Manual (sample)",
          "description": "Sample service manual.",
          "manufacturer": "Alliance Laundry Systems",
          "brand": "Speed Queen",
          "model": "SC60",
          "serial_range": null,
          "document_type": "service_manual",
          "part_number": null,
          "revision": "Rev 4",
          "published_at": "2023-05-01",
          "source_url": null,
          "access_method": "internal",
          "metadata": {},
          "relevance_score": 0.9
        },
        {
          "provider_id": "mock",
          "source_reference": "mock-part-f8524501",
          "result_type": "part",
          "data_origin": "mock",
          "title": "Door lock assembly (sample part)",
          "part_number": "F8524501",
          "relevance_score": 0.7
        }
      ]
    }
  ],
  "providers": [
    {"provider_id": "mock", "status": "success", "latency_ms": 1.2, "result_count": 2},
    {"provider_id": "alliance", "status": "timed_out", "latency_ms": 10000, "result_count": 0, "error": "TimeoutError"}
  ]
}
''';

void main() {
  _generationMatchTests();
  group('SearchResponse.fromJson', () {
    test('parses a full response', () {
      final response = SearchResponse.fromJson(
        jsonDecode(sampleResponseJson) as Map<String, dynamic>,
      );

      expect(response.query, 'SC60');
      expect(response.detectedQueryType, 'model');
      expect(response.totalResults, 2);
      expect(response.groups, hasLength(1));

      final group = response.groups.single;
      expect(group.model, 'SC60');
      expect(group.results, hasLength(2));

      final doc = group.results.first;
      expect(doc.title, 'SC60 Service Manual (sample)');
      expect(doc.dataOrigin, 'mock');
      expect(doc.documentType, 'service_manual');
      expect(doc.revision, 'Rev 4');
      expect(doc.relevanceScore, 0.9);
    });

    test('tolerates missing optional fields', () {
      final response = SearchResponse.fromJson(
        jsonDecode(sampleResponseJson) as Map<String, dynamic>,
      );
      final part = response.groups.single.results[1];
      expect(part.description, isNull);
      expect(part.documentType, isNull);
      expect(part.partNumber, 'F8524501');
    });

    test('exposes degraded providers', () {
      final response = SearchResponse.fromJson(
        jsonDecode(sampleResponseJson) as Map<String, dynamic>,
      );
      expect(response.degradedProviders.map((p) => p.providerId), ['alliance']);
      expect(response.providers.first.isDegraded, isFalse);
    });
  });

  group('ProviderOutcome status handling', () {
    ProviderOutcome outcome(String status) =>
        ProviderOutcome(providerId: 'alliance', status: status);

    test('reauth and forbidden count as degraded', () {
      expect(outcome('reauthentication_required').isDegraded, isTrue);
      expect(outcome('forbidden').isDegraded, isTrue);
      expect(outcome('failed').isDegraded, isTrue);
      expect(outcome('timed_out').isDegraded, isTrue);
      expect(outcome('success').isDegraded, isFalse);
      expect(outcome('disabled').isDegraded, isFalse);
    });

    test('status labels are human readable', () {
      expect(outcome('reauthentication_required').statusLabel, 'needs sign-in');
      expect(outcome('forbidden').statusLabel, 'access refused');
      expect(outcome('failed').statusLabel, 'unavailable');
      expect(outcome('timed_out').statusLabel, 'timed out');
    });
  });
}

void _generationMatchTests() {
  group('generation match', () {
    SearchResult result(Map<String, String> metadata) => SearchResult(
      providerId: 'alliance',
      sourceReference: 'als-model-395125',
      resultType: 'model',
      dataOrigin: 'live',
      title: 'BA120N',
      metadata: metadata,
    );

    test('flagged when the backend identified the covering generation', () {
      expect(
        result(const {'generation_match': 'exact'}).isGenerationMatch,
        isTrue,
      );
    });

    test('not flagged without the marker', () {
      expect(result(const {'manual_id': '16677'}).isGenerationMatch, isFalse);
      expect(result(const {}).isGenerationMatch, isFalse);
    });

    test('parses through from a backend payload', () {
      final parsed = SearchResult.fromJson(const {
        'provider_id': 'alliance',
        'source_reference': 'als-model-395125',
        'result_type': 'model',
        'data_origin': 'live',
        'title': 'BA120N',
        'metadata': {'generation_match': 'exact', 'manual_id': '16892'},
      });
      expect(parsed.isGenerationMatch, isTrue);
      expect(parsed.documentRef, isNull); // no model_id, so no ref
    });
  });
}
