import 'package:flutter/material.dart';

import '../models/search.dart';
import 'badges.dart';

/// One search result: title, description, and scannable metadata badges.
/// When [onDocuments] is provided a trailing button opens the provider's
/// document list for this result (Milestone 10).
class ResultCard extends StatelessWidget {
  const ResultCard({
    super.key,
    required this.result,
    this.onTap,
    this.onDocuments,
    this.onDrawings,
  });

  final SearchResult result;
  final VoidCallback? onTap;
  final VoidCallback? onDocuments;
  final VoidCallback? onDrawings;

  IconData get _icon => switch (result.resultType) {
    'document' => Icons.menu_book_outlined,
    'part' => Icons.settings_outlined,
    'fault_code' => Icons.error_outline,
    'diagram' => Icons.schema_outlined,
    'bulletin' => Icons.campaign_outlined,
    _ => Icons.description_outlined,
  };

  /// Whether this result is a machine rather than a document or part.
  bool get _isMachine => result.resultType == 'model';

  /// The badges worth the space they take.
  ///
  /// A machine card carries almost none: the provider, "live" and the
  /// document type said nothing a technician standing at the machine
  /// needed, and they crowded out the one badge that matters. Document and
  /// part results keep their identifying metadata, which is often the only
  /// place a part number appears.
  ///
  /// Data origin is the exception to the tidying: anything not live —
  /// cached, mock, fixture — stays labelled on every result, because data
  /// that is not current must never pass for data that is.
  List<Widget> get badges => [
    if (result.isGenerationMatch) const MatchBadge('matches this serial'),
    if (result.dataOrigin != 'live') DataOriginBadge(result.dataOrigin),
    if (!_isMachine) ...[
      if (result.documentType != null)
        InfoBadge(result.documentType!.replaceAll('_', ' ')),
      if (result.partNumber != null) InfoBadge(result.partNumber!),
      if (result.revision != null) InfoBadge(result.revision!),
    ],
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(_icon, color: theme.colorScheme.primary, size: 28),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(result.title, style: theme.textTheme.titleSmall),
                    if (result.description != null) ...[
                      const SizedBox(height: 4),
                      Text(
                        result.description!,
                        style: theme.textTheme.bodySmall,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                    if (badges.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Wrap(spacing: 6, runSpacing: 4, children: badges),
                    ],
                  ],
                ),
              ),
              if (onDrawings != null)
                IconButton(
                  tooltip: 'Assembly drawings',
                  icon: const Icon(Icons.schema_outlined),
                  color: theme.colorScheme.primary,
                  onPressed: onDrawings,
                ),
              if (onDocuments != null)
                IconButton(
                  tooltip: 'Documents',
                  icon: const Icon(Icons.picture_as_pdf_outlined),
                  color: theme.colorScheme.primary,
                  onPressed: onDocuments,
                ),
            ],
          ),
        ),
      ),
    );
  }
}
