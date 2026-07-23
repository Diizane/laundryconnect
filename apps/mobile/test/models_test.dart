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
}
