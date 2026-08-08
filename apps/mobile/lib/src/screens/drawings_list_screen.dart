import 'dart:async';

import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../models/provider_documents.dart';
import '../models/search.dart';
import 'drawing_screen.dart';

/// Assembly drawings available for one machine.
///
/// The search box looks inside the drawings, not just at their names: a
/// technician after the drive belt does not know it lives in "Drive" —
/// that is the thing they are trying to find out. Typing "belt" asks the
/// backend which drawings contain a matching part, and each suggestion
/// shows why it was made.
///
/// Every drawing stays listed when the box is empty. The name qualifiers
/// ("Cabinet — A, IA and WMA Models") are provider prose, and hiding one a
/// technician needs is worse than showing extras.
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

/// What the search box is showing.
sealed class _SearchState {
  const _SearchState();
}

class _NotSearching extends _SearchState {
  const _NotSearching();
}

class _Searching extends _SearchState {
  const _Searching();
}

class _SearchFailed extends _SearchState {
  const _SearchFailed(this.message);

  final String message;
}

class _Found extends _SearchState {
  const _Found(this.query, this.matches);

  final String query;
  final List<DrawingSearchMatch> matches;
}

class _DrawingsListScreenState extends State<DrawingsListScreen> {
  _ListState _state = const _Loading();
  _SearchState _search = const _NotSearching();
  final _filter = TextEditingController();
  String _query = '';
  Timer? _debounce;
  int _searchSequence = 0;

  /// Long enough not to fire on every keystroke, short enough not to feel
  /// like waiting.
  static const _debounceDelay = Duration(milliseconds: 400);

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _debounce?.cancel();
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

  void _onQueryChanged(String value) {
    setState(() => _query = value);
    _debounce?.cancel();
    final needle = value.trim();
    if (needle.isEmpty) {
      setState(() => _search = const _NotSearching());
      return;
    }
    _debounce = Timer(_debounceDelay, () => _runSearch(needle));
  }

  Future<void> _runSearch(String needle) async {
    final ref = widget.result.documentRef;
    if (ref == null || needle.isEmpty) return;
    final sequence = ++_searchSequence;
    setState(() => _search = const _Searching());
    try {
      final matches = await widget.api.searchDrawings(
        widget.result.providerId,
        ref,
        needle,
      );
      // A slower earlier search must not overwrite a later one.
      if (!mounted || sequence != _searchSequence) return;
      setState(() => _search = _Found(needle, matches));
    } on ApiException catch (error) {
      if (!mounted || sequence != _searchSequence) return;
      setState(() => _search = _SearchFailed(error.message));
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
        _Loaded(:final drawings) => Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
              child: TextField(
                key: const Key('drawings-filter'),
                controller: _filter,
                onChanged: _onQueryChanged,
                decoration: InputDecoration(
                  isDense: true,
                  prefixIcon: const Icon(Icons.search, size: 20),
                  hintText: 'Find a part or drawing — e.g. belt, door, panel',
                  suffixIcon: _query.isEmpty
                      ? null
                      : IconButton(
                          icon: const Icon(Icons.clear, size: 18),
                          onPressed: () {
                            _filter.clear();
                            _onQueryChanged('');
                          },
                        ),
                ),
              ),
            ),
            Expanded(child: _results(drawings)),
          ],
        ),
      },
    );
  }

  Widget _results(List<DrawingSummary> drawings) {
    final theme = Theme.of(context);
    switch (_search) {
      case _NotSearching():
        return _AllDrawings(drawings: drawings, onOpen: _open);

      case _Searching():
        return Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: 16),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 32),
              child: Text(
                'Looking through this machine’s parts lists. The first '
                'search on a machine takes longer.',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall,
              ),
            ),
          ],
        );

      case _SearchFailed(:final message):
        return Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(message, textAlign: TextAlign.center),
                const SizedBox(height: 12),
                OutlinedButton(
                  onPressed: () => _runSearch(_query.trim()),
                  child: const Text('Try again'),
                ),
              ],
            ),
          ),
        );

      case _Found(:final query, :final matches) when matches.isEmpty:
        return Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(
              'Nothing matching "$query" in this machine’s drawings.',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall,
            ),
          ),
        );

      case _Found(:final matches):
        return ListView.builder(
          itemCount: matches.length,
          itemBuilder: (context, index) {
            final match = matches[index];
            return ListTile(
              leading: Icon(
                Icons.schema_outlined,
                color: theme.colorScheme.primary,
              ),
              title: Text(match.title),
              // Why this drawing was suggested: the part that matched, with
              // the number that gets ordered.
              subtitle: match.matches.isEmpty
                  ? null
                  : Text(
                      match.matches
                          .take(3)
                          .map((p) => '${p.description} · ${p.partNumber}')
                          .join('\n'),
                      style: theme.textTheme.bodySmall,
                    ),
              isThreeLine: match.matches.length > 1,
              onTap: () => _open(match.summary),
            );
          },
        );
    }
  }
}

class _AllDrawings extends StatelessWidget {
  const _AllDrawings({required this.drawings, required this.onOpen});

  final List<DrawingSummary> drawings;
  final void Function(DrawingSummary) onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView.builder(
      itemCount: drawings.length,
      itemBuilder: (context, index) {
        final drawing = drawings[index];
        return ListTile(
          leading: Icon(
            Icons.schema_outlined,
            color: theme.colorScheme.primary,
          ),
          title: Text(drawing.title),
          onTap: () => onOpen(drawing),
        );
      },
    );
  }
}
