/// Models mirroring the backend search schemas
/// (services/api/app/schemas/search.py). Parsing is tolerant of missing
/// optional fields but strict about the ones the UI depends on.
library;

/// One normalised search result from a provider.
class SearchResult {
  const SearchResult({
    required this.providerId,
    required this.sourceReference,
    required this.resultType,
    required this.dataOrigin,
    required this.title,
    this.description,
    this.manufacturer,
    this.brand,
    this.model,
    this.serialRange,
    this.documentType,
    this.partNumber,
    this.revision,
    this.sourceUrl,
    this.metadata = const {},
    this.relevanceScore = 0,
  });

  final String providerId;
  final String sourceReference;
  final String resultType;

  /// mock / manual / live / cached — always shown as a badge so mock or
  /// cached data can never be mistaken for live provider data.
  final String dataOrigin;
  final String title;
  final String? description;
  final String? manufacturer;
  final String? brand;
  final String? model;
  final String? serialRange;
  final String? documentType;
  final String? partNumber;
  final String? revision;
  final String? sourceUrl;

  /// Provider-supplied metadata (string key/values). For Alliance model
  /// results this carries the catalog identifiers used to build the
  /// document-discovery reference.
  final Map<String, String> metadata;
  final double relevanceScore;

  /// The reference this result's documents can be discovered with, or null
  /// when the result has none. The value is only ever sent back to the
  /// LaundryConnect backend — never to a provider.
  String? get documentRef {
    if (providerId == 'alliance') {
      final manualId = metadata['manual_id'];
      final modelId = metadata['model_id'];
      if (manualId != null && modelId != null) return '$manualId:$modelId';
      return null;
    }
    if (providerId == 'mock') return sourceReference;
    return null;
  }

  factory SearchResult.fromJson(Map<String, dynamic> json) => SearchResult(
    providerId: json['provider_id'] as String,
    sourceReference: json['source_reference'] as String,
    resultType: json['result_type'] as String,
    dataOrigin: json['data_origin'] as String,
    title: json['title'] as String,
    description: json['description'] as String?,
    manufacturer: json['manufacturer'] as String?,
    brand: json['brand'] as String?,
    model: json['model'] as String?,
    serialRange: json['serial_range'] as String?,
    documentType: json['document_type'] as String?,
    partNumber: json['part_number'] as String?,
    revision: json['revision'] as String?,
    sourceUrl: json['source_url'] as String?,
    metadata:
        (json['metadata'] as Map<String, dynamic>?)?.map(
          (key, value) => MapEntry(key, value.toString()),
        ) ??
        const {},
    relevanceScore: (json['relevance_score'] as num?)?.toDouble() ?? 0,
  );
}

/// Results grouped under one machine/model ("other" group when model is null).
class MachineGroup {
  const MachineGroup({
    this.manufacturer,
    this.brand,
    this.model,
    required this.results,
  });

  final String? manufacturer;
  final String? brand;
  final String? model;
  final List<SearchResult> results;

  factory MachineGroup.fromJson(Map<String, dynamic> json) => MachineGroup(
    manufacturer: json['manufacturer'] as String?,
    brand: json['brand'] as String?,
    model: json['model'] as String?,
    results: (json['results'] as List<dynamic>)
        .map((r) => SearchResult.fromJson(r as Map<String, dynamic>))
        .toList(),
  );
}

/// Per-provider outcome of a search (success / failed / timed_out / disabled).
class ProviderOutcome {
  const ProviderOutcome({
    required this.providerId,
    required this.status,
    this.latencyMs,
    this.resultCount = 0,
  });

  final String providerId;
  final String status;
  final double? latencyMs;
  final int resultCount;

  bool get isDegraded =>
      status == 'failed' ||
      status == 'timed_out' ||
      status == 'reauthentication_required' ||
      status == 'forbidden';

  /// A short, human-readable label for a degraded provider outcome.
  String get statusLabel => switch (status) {
    'timed_out' => 'timed out',
    'reauthentication_required' => 'needs sign-in',
    'forbidden' => 'access refused',
    'failed' => 'unavailable',
    _ => status,
  };

  factory ProviderOutcome.fromJson(Map<String, dynamic> json) =>
      ProviderOutcome(
        providerId: json['provider_id'] as String,
        status: json['status'] as String,
        latencyMs: (json['latency_ms'] as num?)?.toDouble(),
        resultCount: json['result_count'] as int? ?? 0,
      );
}

class SearchResponse {
  const SearchResponse({
    required this.query,
    required this.detectedQueryType,
    required this.totalResults,
    required this.groups,
    required this.providers,
  });

  final String query;
  final String detectedQueryType;
  final int totalResults;
  final List<MachineGroup> groups;
  final List<ProviderOutcome> providers;

  List<ProviderOutcome> get degradedProviders =>
      providers.where((p) => p.isDegraded).toList();

  factory SearchResponse.fromJson(Map<String, dynamic> json) => SearchResponse(
    query: json['query'] as String,
    detectedQueryType: json['detected_query_type'] as String,
    totalResults: json['total_results'] as int,
    groups: (json['groups'] as List<dynamic>)
        .map((g) => MachineGroup.fromJson(g as Map<String, dynamic>))
        .toList(),
    providers: (json['providers'] as List<dynamic>)
        .map((p) => ProviderOutcome.fromJson(p as Map<String, dynamic>))
        .toList(),
  );
}
