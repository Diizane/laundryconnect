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
}
