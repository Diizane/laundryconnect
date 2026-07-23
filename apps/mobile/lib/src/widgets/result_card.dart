import 'package:flutter/material.dart';

import '../models/search.dart';
import 'badges.dart';

/// One search result: title, description, and scannable metadata badges.
class ResultCard extends StatelessWidget {
  const ResultCard({super.key, required this.result});

  final SearchResult result;

  IconData get _icon => switch (result.resultType) {
    'document' => Icons.menu_book_outlined,
    'part' => Icons.settings_outlined,
    'fault_code' => Icons.error_outline,
    'diagram' => Icons.schema_outlined,
    'bulletin' => Icons.campaign_outlined,
    _ => Icons.description_outlined,
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
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
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 6,
                    runSpacing: 4,
                    children: [
                      DataOriginBadge(result.dataOrigin),
                      InfoBadge(result.providerId),
                      if (result.documentType != null)
                        InfoBadge(result.documentType!.replaceAll('_', ' ')),
                      if (result.partNumber != null)
                        InfoBadge(result.partNumber!),
                      if (result.revision != null) InfoBadge(result.revision!),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
