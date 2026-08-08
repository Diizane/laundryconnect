import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../api/api_client.dart';
import '../models/provider_documents.dart';

/// One assembly drawing: the exploded diagram and its parts list.
///
/// The diagram is vector, so it zooms cleanly. Callout numbers inside it
/// are outlines rather than text (see docs/MILESTONE_15), so they are not
/// tappable — the technician reads a number off the diagram and finds it in
/// the list, which is searchable by number, part number or description.
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
                  ? InteractiveViewer(
                      // Exploded diagrams are dense; allow real zoom.
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
                    )
                  : Center(
                      child: Text(
                        'No diagram available for this drawing.',
                        style: theme.textTheme.bodyMedium,
                      ),
                    ),
            ),
            const Divider(height: 1),
            Expanded(
              flex: 2,
              child: _PartsList(
                parts: drawing.parts,
                controller: _filter,
                query: _query,
                onQueryChanged: (value) => setState(() => _query = value),
              ),
            ),
          ],
        ),
      },
    );
  }
}

class _PartsList extends StatelessWidget {
  const _PartsList({
    required this.parts,
    required this.controller,
    required this.query,
    required this.onQueryChanged,
  });

  final List<DrawingPart> parts;
  final TextEditingController controller;
  final String query;
  final ValueChanged<String> onQueryChanged;

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
                return ListTile(
                  dense: true,
                  // The callout number, so a technician can go from the
                  // number on the diagram straight to the row.
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
                );
              },
            ),
          ),
      ],
    );
  }
}
