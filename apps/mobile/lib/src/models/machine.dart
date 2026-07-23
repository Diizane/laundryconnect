/// Models mirroring the backend machine workspace schemas
/// (services/api/app/schemas/machines.py).
library;

class MachineSummary {
  const MachineSummary({
    required this.id,
    required this.modelNumber,
    required this.brand,
    required this.manufacturer,
    this.machineType,
    this.family,
  });

  final String id;
  final String modelNumber;
  final String brand;
  final String manufacturer;
  final String? machineType;
  final String? family;

  factory MachineSummary.fromJson(Map<String, dynamic> json) => MachineSummary(
    id: json['id'] as String,
    modelNumber: json['model_number'] as String,
    brand: json['brand'] as String,
    manufacturer: json['manufacturer'] as String,
    machineType: json['machine_type'] as String?,
    family: json['family'] as String?,
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'model_number': modelNumber,
    'brand': brand,
    'manufacturer': manufacturer,
    'machine_type': machineType,
    'family': family,
  };
}

class DocumentItem {
  const DocumentItem({
    required this.id,
    required this.title,
    required this.documentType,
    required this.provider,
    required this.origin,
    this.sourceUrl,
    this.revision,
    this.publishedAt,
    this.language,
  });

  final String id;
  final String title;
  final String documentType;
  final String provider;

  /// seeded_sample / live / uploaded / cached — always shown as a badge so
  /// sample content can never pass as official provider data.
  final String origin;
  final String? sourceUrl;
  final String? revision;
  final String? publishedAt;
  final String? language;

  factory DocumentItem.fromJson(Map<String, dynamic> json) => DocumentItem(
    id: json['id'] as String,
    title: json['title'] as String,
    documentType: json['document_type'] as String,
    provider: json['provider'] as String,
    origin: json['origin'] as String? ?? 'unknown',
    sourceUrl: json['source_url'] as String?,
    revision: json['revision'] as String?,
    publishedAt: json['published_at'] as String?,
    language: json['language'] as String?,
  );
}

class DocumentCategory {
  const DocumentCategory({required this.documentType, required this.documents});

  final String documentType;
  final List<DocumentItem> documents;

  factory DocumentCategory.fromJson(Map<String, dynamic> json) =>
      DocumentCategory(
        documentType: json['document_type'] as String,
        documents: (json['documents'] as List<dynamic>)
            .map((d) => DocumentItem.fromJson(d as Map<String, dynamic>))
            .toList(),
      );
}

class MachineDocuments {
  const MachineDocuments({required this.machine, required this.categories});

  final MachineSummary machine;
  final List<DocumentCategory> categories;

  factory MachineDocuments.fromJson(Map<String, dynamic> json) =>
      MachineDocuments(
        machine: MachineSummary.fromJson(
          json['machine'] as Map<String, dynamic>,
        ),
        categories: (json['categories'] as List<dynamic>)
            .map((c) => DocumentCategory.fromJson(c as Map<String, dynamic>))
            .toList(),
      );
}
