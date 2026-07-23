import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Compact metadata chip used on result cards (provider, type, revision...).
class InfoBadge extends StatelessWidget {
  const InfoBadge(this.label, {super.key, this.color});

  final String label;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final background = color ?? AppColors.navy.withValues(alpha: 0.08);
    final foreground = color != null ? Colors.white : AppColors.navy;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: foreground,
        ),
      ),
    );
  }
}

/// Data-origin badge: mock and cached data must be visibly labelled so it is
/// never mistaken for live provider data.
class DataOriginBadge extends StatelessWidget {
  const DataOriginBadge(this.origin, {super.key});

  final String origin;

  @override
  Widget build(BuildContext context) {
    final color = switch (origin) {
      'live' => AppColors.teal,
      'cached' => AppColors.warning,
      _ => Colors.blueGrey, // mock / seeded_sample / manual sample data
    };
    return InfoBadge(origin.replaceAll('_', ' ').toUpperCase(), color: color);
  }
}
