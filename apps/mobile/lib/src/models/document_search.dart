/// Models mirroring the backend document schemas
/// (services/api/app/schemas/documents.py).
library;

class PageSearchHit {
  const PageSearchHit({
    required this.documentId,
    required this.documentTitle,
    required this.provider,
    required this.pageNumber,
    required this.snippet,
  });

  final String documentId;
  final String documentTitle;
  final String provider;
  final int pageNumber;
  final String snippet;

  factory PageSearchHit.fromJson(Map<String, dynamic> json) => PageSearchHit(
    documentId: json['document_id'] as String,
    documentTitle: json['document_title'] as String,
    provider: json['provider'] as String,
    pageNumber: json['page_number'] as int,
    snippet: json['snippet'] as String,
  );
}

class DocumentSearchResult {
  const DocumentSearchResult({
    required this.query,
    required this.totalHits,
    required this.hits,
  });

  final String query;
  final int totalHits;
  final List<PageSearchHit> hits;

  factory DocumentSearchResult.fromJson(Map<String, dynamic> json) =>
      DocumentSearchResult(
        query: json['query'] as String,
        totalHits: json['total_hits'] as int,
        hits: (json['hits'] as List<dynamic>)
            .map((h) => PageSearchHit.fromJson(h as Map<String, dynamic>))
            .toList(),
      );
}

class DocumentPageContent {
  const DocumentPageContent({
    required this.pageNumber,
    required this.textContent,
  });

  final int pageNumber;
  final String textContent;

  factory DocumentPageContent.fromJson(Map<String, dynamic> json) =>
      DocumentPageContent(
        pageNumber: json['page_number'] as int,
        textContent: json['text_content'] as String,
      );
}
