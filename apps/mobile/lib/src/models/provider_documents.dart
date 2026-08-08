/// Models mirroring the backend provider-document schemas
/// (services/api/app/schemas/provider_documents.py).
///
/// A document is referenced ONLY by its opaque backend `token` — the app
/// never sees or constructs a provider URL or path. Tokens expire after a
/// short backend-configured lifetime; rediscovery mints fresh ones.
library;

import 'dart:typed_data';

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

  /// Whether this document is usable by an English-speaking technician.
  ///
  /// True when the provider lists English among its languages (many
  /// documents are multi-language files that include English), and also
  /// when no language is listed at all — an unclassified document is shown
  /// rather than silently hidden, since hiding a manual a technician needs
  /// is worse than showing one they cannot read.
  bool get isEnglish {
    if (languages.isEmpty) return true;
    return languages.any((language) {
      final normalised = language.trim().toLowerCase();
      return normalised == 'en' || normalised.startsWith('english');
    });
  }

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

  /// Documents an English-speaking technician can use. Provider catalogues
  /// carry translations of the same manual for every market; those are
  /// noise here. Documents with no language listed are kept (see
  /// [ProviderDocument.isEnglish]).
  List<ProviderDocument> get englishDocuments =>
      documents.where((d) => d.isEnglish).toList();

  /// How many documents were hidden as non-English.
  int get hiddenNonEnglishCount => documents.length - englishDocuments.length;

  /// English documents grouped by type, ordered so the ones a technician
  /// standing at a machine reaches for come first. Providers list compliance
  /// paperwork (declarations of conformity) before the service manuals,
  /// which buries what matters — this reverses that.
  List<DocumentGroup> get groups {
    final byType = <String, List<ProviderDocument>>{};
    for (final document in englishDocuments) {
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

/// One heading from a document's embedded table of contents.
class ContentsEntry {
  const ContentsEntry({
    required this.title,
    required this.pageNumber,
    this.depth = 0,
  });

  final String title;
  final int pageNumber;
  final int depth;

  factory ContentsEntry.fromJson(Map<String, dynamic> json) => ContentsEntry(
    title: json['title'] as String,
    pageNumber: json['page_number'] as int,
    depth: json['depth'] as int? ?? 0,
  );
}

/// What a document offers for navigation and search.
class DocumentContents {
  const DocumentContents({
    required this.pageCount,
    required this.searchable,
    required this.searchablePages,
    this.contents = const [],
  });

  final int pageCount;

  /// False when the PDF carries no usable text layer. Some real manuals
  /// embed fonts without character maps, so a search over them can only
  /// ever return nothing — the UI says so rather than looking broken.
  final bool searchable;
  final int searchablePages;
  final List<ContentsEntry> contents;

  bool get hasContents => contents.isNotEmpty;

  factory DocumentContents.fromJson(Map<String, dynamic> json) =>
      DocumentContents(
        pageCount: json['page_count'] as int,
        searchable: json['searchable'] as bool,
        searchablePages: json['searchable_pages'] as int? ?? 0,
        contents:
            (json['contents'] as List<dynamic>?)
                ?.map((e) => ContentsEntry.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
      );
}

/// One page-cited match from searching inside a document.
class DocumentSearchHit {
  const DocumentSearchHit({required this.pageNumber, required this.snippet});

  final int pageNumber;
  final String snippet;

  factory DocumentSearchHit.fromJson(Map<String, dynamic> json) =>
      DocumentSearchHit(
        pageNumber: json['page_number'] as int,
        snippet: json['snippet'] as String,
      );
}

class DocumentSearchResults {
  const DocumentSearchResults({
    required this.query,
    required this.searchable,
    required this.hits,
  });

  final String query;
  final bool searchable;
  final List<DocumentSearchHit> hits;

  factory DocumentSearchResults.fromJson(Map<String, dynamic> json) =>
      DocumentSearchResults(
        query: json['query'] as String,
        searchable: json['searchable'] as bool,
        hits:
            (json['hits'] as List<dynamic>?)
                ?.map(
                  (e) => DocumentSearchHit.fromJson(e as Map<String, dynamic>),
                )
                .toList() ??
            const [],
      );
}

/// A downloaded document plus where the bytes actually came from.
///
/// The backend serves a stored copy when the provider cannot be reached —
/// an expired session or an outage — which is what keeps a technician
/// working mid-job. That must be visible rather than silent, consistent
/// with the project's rule that non-live data is never presented as live.
class DownloadedDocument {
  const DownloadedDocument({
    required this.bytes,
    required this.origin,
    this.ageSeconds = 0,
  });

  final Uint8List bytes;

  /// 'live' when fetched from the provider just now, 'cached' when served
  /// from the server's stored copy.
  final String origin;

  /// How long since that copy was last confirmed current. Zero for live
  /// documents and for cached copies the provider has just revalidated.
  final int ageSeconds;

  bool get isCached => origin == 'cached';

  /// True only when the copy is genuinely stale — served without the
  /// provider confirming it. A revalidated copy reports zero age and needs
  /// no warning.
  bool get isStale => isCached && ageSeconds > 0;

  /// Short human phrasing of the age, for a badge.
  String get ageLabel {
    final days = ageSeconds ~/ 86400;
    if (days >= 1) return days == 1 ? '1 day old' : '$days days old';
    final hours = ageSeconds ~/ 3600;
    if (hours >= 1) return hours == 1 ? '1 hour old' : '$hours hours old';
    return 'just now';
  }
}
