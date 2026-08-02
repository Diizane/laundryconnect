/// Models mirroring the backend provider-document schemas
/// (services/api/app/schemas/provider_documents.py).
///
/// A document is referenced ONLY by its opaque backend `token` — the app
/// never sees or constructs a provider URL or path. Tokens expire after a
/// short backend-configured lifetime; rediscovery mints fresh ones.
library;

/// One document a provider offers for a machine, with client-safe metadata.
class ProviderDocument {
  const ProviderDocument({
    required this.token,
    required this.title,
    this.documentType,
    this.partNumber,
    this.comment,
    this.languages = const [],
    this.category,
    this.filename,
    required this.available,
    required this.dataOrigin,
  });

  /// Opaque download reference; null when the provider lists the document
  /// without a downloadable file.
  final String? token;
  final String title;
  final String? documentType;
  final String? partNumber;
  final String? comment;
  final List<String> languages;
  final String? category;
  final String? filename;
  final bool available;
  final String dataOrigin;

  bool get isDownloadable => available && token != null;

  factory ProviderDocument.fromJson(Map<String, dynamic> json) =>
      ProviderDocument(
        token: json['token'] as String?,
        title: json['title'] as String,
        documentType: json['document_type'] as String?,
        partNumber: json['part_number'] as String?,
        comment: json['comment'] as String?,
        languages:
            (json['languages'] as List<dynamic>?)?.cast<String>() ?? const [],
        category: json['category'] as String?,
        filename: json['filename'] as String?,
        available: json['available'] as bool,
        dataOrigin: json['data_origin'] as String,
      );
}

class DocumentDiscovery {
  const DocumentDiscovery({required this.providerId, required this.documents});

  final String providerId;
  final List<ProviderDocument> documents;

  factory DocumentDiscovery.fromJson(Map<String, dynamic> json) =>
      DocumentDiscovery(
        providerId: json['provider_id'] as String,
        documents: (json['documents'] as List<dynamic>)
            .map((d) => ProviderDocument.fromJson(d as Map<String, dynamic>))
            .toList(),
      );

  /// Documents grouped by type, ordered so the ones a technician standing at
  /// a machine reaches for come first. Providers list compliance paperwork
  /// (declarations of conformity) before the service manuals, which buries
  /// what matters — this reverses that.
  List<DocumentGroup> get groups {
    final byType = <String, List<ProviderDocument>>{};
    for (final document in documents) {
      final key = (document.documentType ?? 'Other').trim();
      byType.putIfAbsent(key.isEmpty ? 'Other' : key, () => []).add(document);
    }
    final entries = byType.entries
        .map((e) => DocumentGroup(documentType: e.key, documents: e.value))
        .toList();
    entries.sort((a, b) {
      final byRank = a.rank.compareTo(b.rank);
      return byRank != 0 ? byRank : a.documentType.compareTo(b.documentType);
    });
    return entries;
  }
}

/// One collapsible section of the document list.
class DocumentGroup {
  const DocumentGroup({required this.documentType, required this.documents});

  final String documentType;
  final List<ProviderDocument> documents;

  int get downloadableCount => documents.where((d) => d.isDownloadable).length;

  /// Field-usefulness ranking (lower sorts first). Matched loosely because
  /// providers word these inconsistently ("Technical Mnl", "Service
  /// Manual", …).
  int get rank {
    final type = documentType.toLowerCase();
    bool has(List<String> needles) => needles.any(type.contains);

    if (has(['technical', 'service', 'repair'])) return 0;
    if (has(['part'])) return 1;
    if (has(['wiring', 'schematic', 'diagram'])) return 2;
    if (has(['install', 'operation', 'maintenance', 'user', 'owner'])) return 3;
    if (has(['bulletin', 'instruction'])) return 4;
    if (has(['conformity', 'declaration', 'compliance', 'certificate'])) {
      return 6; // compliance paperwork: last, it is rarely wanted on a job
    }
    return 5;
  }
}
