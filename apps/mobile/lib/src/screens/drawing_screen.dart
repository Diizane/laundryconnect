import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../api/api_client.dart';
import '../models/provider_documents.dart';

/// One assembly drawing: the exploded diagram and its parts list.
///
/// The diagram is vector, so it zooms cleanly. Where the provider labels its
/// callout markers in the markup, tapping a number on the diagram names the
/// part; where it does not — one of the export pipelines draws callouts
/// anonymously — the diagram is still shown and the parts list is still
/// searchable by number, part number or description. Nothing is guessed:
/// a drawing with no reliable markers simply has no tap targets.
class DrawingScreen extends StatefulWidget {
  const DrawingScreen({
    super.key,
    required this.title,
    required this.providerId,
    required this.token,
    required this.api,
  });

  final String title;
  final String providerId;
  final String token;
  final ProviderDocumentsApi api;

  @override
  State<DrawingScreen> createState() => _DrawingScreenState();
}

sealed class _DrawingState {
  const _DrawingState();
}

class _Loading extends _DrawingState {
  const _Loading();
}

class _Failed extends _DrawingState {
  const _Failed(this.message);

  final String message;
}

class _Loaded extends _DrawingState {
  const _Loaded(this.drawing);

  final DrawingDetail drawing;
}

class _DrawingScreenState extends State<DrawingScreen> {
  _DrawingState _state = const _Loading();
  final _filter = TextEditingController();
  String _query = '';
  String? _selected;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _filter.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _state = const _Loading());
    try {
      final drawing = await widget.api.fetchDrawing(
        widget.providerId,
        widget.token,
      );
      if (mounted) setState(() => _state = _Loaded(drawing));
    } on ApiException catch (error) {
      if (mounted) setState(() => _state = _Failed(error.message));
    }
  }

  void _selectFromDiagram(DrawingDetail drawing, String reference) {
    setState(() => _selected = reference);
    final part = drawing.partFor(reference);
    if (part == null) return; // backend drops these, but never assume
    showModalBottomSheet<void>(
      context: context,
      builder: (context) => _PartSheet(reference: reference, part: part),
    ).whenComplete(() {
      if (mounted) setState(() => _selected = null);
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.title, maxLines: 1, overflow: TextOverflow.ellipsis),
      ),
      body: switch (_state) {
        _Loading() => const Center(child: CircularProgressIndicator()),
        _Failed(:final message) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.cloud_off,
                  size: 40,
                  color: theme.colorScheme.primary,
                ),
                const SizedBox(height: 12),
                Text(message, textAlign: TextAlign.center),
                const SizedBox(height: 12),
                OutlinedButton(onPressed: _load, child: const Text('Retry')),
              ],
            ),
          ),
        ),
        _Loaded(:final drawing) => Column(
          children: [
            Expanded(
              flex: 3,
              child: drawing.hasDiagram
                  ? _Diagram(
                      drawing: drawing,
                      selected: _selected,
                      onCalloutTapped: (reference) =>
                          _selectFromDiagram(drawing, reference),
                    )
                  : Center(
                      child: Text(
                        'No diagram available for this drawing.',
                        style: theme.textTheme.bodyMedium,
                      ),
                    ),
            ),
            if (drawing.isInteractive)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Row(
                  children: [
                    Icon(
                      Icons.touch_app_outlined,
                      size: 14,
                      color: theme.colorScheme.primary,
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        'Tap a number on the diagram to identify its part.',
                        style: theme.textTheme.bodySmall,
                      ),
                    ),
                  ],
                ),
              ),
            const Divider(height: 1),
            Expanded(
              flex: 2,
              child: _PartsList(
                parts: drawing.parts,
                controller: _filter,
                query: _query,
                selected: _selected,
                markedReferences: {
                  for (final callout in drawing.callouts) callout.reference,
                },
                onQueryChanged: (value) => setState(() => _query = value),
                onPartTapped: (reference) => setState(
                  () => _selected = _selected == reference ? null : reference,
                ),
              ),
            ),
          ],
        ),
      },
    );
  }
}

/// The zoomable diagram, with a tap target over each labelled callout.
class _Diagram extends StatelessWidget {
  const _Diagram({
    required this.drawing,
    required this.selected,
    required this.onCalloutTapped,
  });

  final DrawingDetail drawing;
  final String? selected;
  final ValueChanged<String> onCalloutTapped;

  /// Smallest tap target, in logical pixels. Deliberately near the marker's
  /// own size: an oversized target on a dense diagram would swallow taps
  /// meant for the callout next door and name the wrong part. Markers scale
  /// with the diagram, so pinching to zoom makes them comfortably tappable.
  static const double _minTarget = 14;

  @override
  Widget build(BuildContext context) {
    final svg = SvgPicture.string(
      drawing.svg,
      fit: BoxFit.fill,
      placeholderBuilder: (_) =>
          const Center(child: CircularProgressIndicator()),
    );
    if (!drawing.isInteractive) {
      return InteractiveViewer(
        minScale: 0.5,
        maxScale: 8,
        child: Center(
          child: SvgPicture.string(
            drawing.svg,
            fit: BoxFit.contain,
            placeholderBuilder: (_) =>
                const Center(child: CircularProgressIndicator()),
          ),
        ),
      );
    }

    final box = drawing.viewBox!;
    final theme = Theme.of(context);
    return LayoutBuilder(
      builder: (context, constraints) {
        // Lay the diagram out at a known size so callout coordinates can be
        // placed on it; BoxFit.contain would leave unknown letterboxing.
        final scale = math.min(
          constraints.maxWidth / box[2],
          constraints.maxHeight / box[3],
        );
        final width = box[2] * scale;
        final height = box[3] * scale;
        return InteractiveViewer(
          minScale: 0.5,
          maxScale: 8,
          child: Center(
            child: SizedBox(
              width: width,
              height: height,
              child: Stack(
                children: [
                  Positioned.fill(child: svg),
                  for (final callout in drawing.callouts)
                    _CalloutTarget(
                      callout: callout,
                      box: box,
                      scale: scale,
                      size: math.max(callout.radius * 2 * scale, _minTarget),
                      highlighted: callout.reference == selected,
                      colour: theme.colorScheme.primary,
                      onTap: () => onCalloutTapped(callout.reference),
                    ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _CalloutTarget extends StatelessWidget {
  const _CalloutTarget({
    required this.callout,
    required this.box,
    required this.scale,
    required this.size,
    required this.highlighted,
    required this.colour,
    required this.onTap,
  });

  final DrawingCallout callout;
  final List<double> box;
  final double scale;
  final double size;
  final bool highlighted;
  final Color colour;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: (callout.x - box[0]) * scale - size / 2,
      top: (callout.y - box[1]) * scale - size / 2,
      width: size,
      height: size,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Semantics(
          button: true,
          label: 'Callout ${callout.reference}',
          child: DecoratedBox(
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              // The provider's own SVG already draws the marker; this only
              // shows which one is selected.
              border: highlighted ? Border.all(color: colour, width: 2) : null,
              color: highlighted ? colour.withValues(alpha: 0.2) : null,
            ),
          ),
        ),
      ),
    );
  }
}

/// What a tapped callout turned out to be.
class _PartSheet extends StatelessWidget {
  const _PartSheet({required this.reference, required this.part});

  final String reference;
  final DrawingPart part;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 16,
                  backgroundColor: theme.colorScheme.primary,
                  child: Text(
                    reference,
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: theme.colorScheme.onPrimary,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    part.description,
                    style: theme.textTheme.titleMedium,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            SelectableText(
              part.partNumber,
              style: theme.textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            if (part.comments != null) ...[
              const SizedBox(height: 8),
              Text(part.comments!, style: theme.textTheme.bodyMedium),
            ],
          ],
        ),
      ),
    );
  }
}

class _PartsList extends StatelessWidget {
  const _PartsList({
    required this.parts,
    required this.controller,
    required this.query,
    required this.selected,
    required this.markedReferences,
    required this.onQueryChanged,
    required this.onPartTapped,
  });

  final List<DrawingPart> parts;
  final TextEditingController controller;
  final String query;
  final String? selected;
  final Set<String> markedReferences;
  final ValueChanged<String> onQueryChanged;
  final ValueChanged<String> onPartTapped;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final visible = parts.where((p) => p.matches(query)).toList();
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
          child: TextField(
            key: const Key('parts-filter'),
            controller: controller,
            onChanged: onQueryChanged,
            decoration: InputDecoration(
              isDense: true,
              prefixIcon: const Icon(Icons.search, size: 20),
              hintText: 'Find a part — number, name, or callout',
              suffixIcon: query.isEmpty
                  ? null
                  : IconButton(
                      icon: const Icon(Icons.clear, size: 18),
                      onPressed: () {
                        controller.clear();
                        onQueryChanged('');
                      },
                    ),
            ),
          ),
        ),
        if (parts.isEmpty)
          Expanded(
            child: Center(
              child: Text(
                'No parts listed for this drawing.',
                style: theme.textTheme.bodySmall,
              ),
            ),
          )
        else if (visible.isEmpty)
          Expanded(
            child: Center(
              child: Text(
                'No parts match "$query".',
                style: theme.textTheme.bodySmall,
              ),
            ),
          )
        else
          Expanded(
            child: ListView.builder(
              itemCount: visible.length,
              itemBuilder: (context, index) {
                final part = visible[index];
                final isSelected = part.reference == selected;
                final isMarked = markedReferences.contains(part.reference);
                return ListTile(
                  dense: true,
                  selected: isSelected,
                  selectedTileColor: theme.colorScheme.primary.withValues(
                    alpha: 0.08,
                  ),
                  // Tapping a row rings its markers on the diagram — the
                  // reverse lookup, for finding where a part sits.
                  onTap: isMarked ? () => onPartTapped(part.reference) : null,
                  // The callout number, so a number read off the diagram can
                  // be found in the list.
                  leading: CircleAvatar(
                    radius: 14,
                    backgroundColor: theme.colorScheme.primary,
                    child: Text(
                      part.reference,
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.onPrimary,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  title: Text(part.description),
                  subtitle: Text(
                    part.comments == null
                        ? part.partNumber
                        : '${part.partNumber} · ${part.comments}',
                  ),
                  trailing: isMarked
                      ? Icon(
                          isSelected
                              ? Icons.my_location
                              : Icons.location_searching,
                          size: 18,
                          color: theme.colorScheme.primary,
                        )
                      : null,
                );
              },
            ),
          ),
      ],
    );
  }
}
