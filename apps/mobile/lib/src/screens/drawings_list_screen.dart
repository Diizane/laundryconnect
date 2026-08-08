import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../models/provider_documents.dart';
import '../models/search.dart';
import 'drawing_screen.dart';

/// Assembly drawings available for one machine.
///
/// A machine can have thirty-plus drawings whose names carry model
/// qualifiers ("Cabinet — A, IA and WMA Models"), so the list is filterable
/// by name. Every drawing stays listed: the qualifiers are provider prose,
/// and hiding one a technician needs is worse than showing extras.
class DrawingsListScreen extends StatefulWidget {
  const DrawingsListScreen({
    super.key,
    required this.result,
    required this.api,
  });

  final SearchResult result;
  final ProviderDocumentsApi api;

  @override
  State<DrawingsListScreen> createState() => _DrawingsListScreenState();
}

sealed class _ListState {
  const _ListState();
}

class _Loading extends _ListState {
  const _Loading();
}

class _Failed extends _ListState {
  const _Failed(this.message, {this.reauthRequired = false});

  final String message;
  final bool reauthRequired;
}

class _Loaded extends _ListState {
  const _Loaded(this.drawings);

  final List<DrawingSummary> drawings;
}

class _DrawingsListScreenState extends State<DrawingsListScreen> {
  _ListState _state = const _Loading();
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
      final ref = widget.result.documentRef;
      if (ref == null) {
        throw const ApiException(
          'This result has no document reference.',
          kind: ApiErrorKind.invalidRequest,
        );
      }
      final drawings = await widget.api.discoverDrawings(
        widget.result.providerId,
        ref,
      );
      if (mounted) setState(() => _state = _Loaded(drawings));
    } on ApiException catch (error) {
      if (mounted) {
        setState(
          () => _state = _Failed(
            error.message,
            reauthRequired: error.kind == ApiErrorKind.reauthenticationRequired,
          ),
        );
      }
    }
  }

  void _open(DrawingSummary drawing) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => DrawingScreen(
          title: drawing.title,
          providerId: widget.result.providerId,
          token: drawing.token,
          api: widget.api,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(
          '${widget.result.bestModel ?? widget.result.title} — drawings',
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ),
      body: switch (_state) {
        _Loading() => const Center(child: CircularProgressIndicator()),
        _Failed(:final message, :final reauthRequired) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  reauthRequired ? Icons.lock_outline : Icons.cloud_off,
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
        _Loaded(:final drawings) when drawings.isEmpty => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(
              'No assembly drawings listed for this machine.',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium,
            ),
          ),
        ),
        _Loaded(:final drawings) => _DrawingsList(
          drawings: drawings,
          controller: _filter,
          query: _query,
          onQueryChanged: (value) => setState(() => _query = value),
          onOpen: _open,
        ),
      },
    );
  }
}

class _DrawingsList extends StatelessWidget {
  const _DrawingsList({
    required this.drawings,
    required this.controller,
    required this.query,
    required this.onQueryChanged,
    required this.onOpen,
  });

  final List<DrawingSummary> drawings;
  final TextEditingController controller;
  final String query;
  final ValueChanged<String> onQueryChanged;
  final void Function(DrawingSummary) onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final needle = query.trim().toLowerCase();
    final visible = needle.isEmpty
        ? drawings
        : drawings
              .where((d) => d.title.toLowerCase().contains(needle))
              .toList();
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
          child: TextField(
            key: const Key('drawings-filter'),
            controller: controller,
            onChanged: onQueryChanged,
            decoration: const InputDecoration(
              isDense: true,
              prefixIcon: Icon(Icons.search, size: 20),
              hintText: 'Filter drawings — e.g. drive, door, panel',
            ),
          ),
        ),
        if (visible.isEmpty)
          Expanded(
            child: Center(
              child: Text(
                'No drawings match "$query".',
                style: theme.textTheme.bodySmall,
              ),
            ),
          )
        else
          Expanded(
            child: ListView.builder(
              itemCount: visible.length,
              itemBuilder: (context, index) {
                final drawing = visible[index];
                return ListTile(
                  leading: Icon(
                    Icons.schema_outlined,
                    color: theme.colorScheme.primary,
                  ),
                  title: Text(drawing.title),
                  onTap: () => onOpen(drawing),
                );
              },
            ),
          ),
      ],
    );
  }
}
