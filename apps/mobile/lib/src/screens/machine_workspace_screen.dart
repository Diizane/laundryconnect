import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../models/machine.dart';
import '../storage/workspace_store.dart';
import '../theme/app_theme.dart';
import '../widgets/badges.dart';
import 'document_search_screen.dart';

/// Machine workspace: model metadata header plus documents grouped by
/// category. Opened from a search result or from recents/bookmarks.
class MachineWorkspaceScreen extends StatefulWidget {
  const MachineWorkspaceScreen({
    super.key,
    required this.machine,
    required this.machinesApi,
    required this.documentsApi,
    required this.store,
  });

  final MachineSummary machine;
  final MachinesApi machinesApi;
  final DocumentsApi documentsApi;
  final WorkspaceStore store;

  @override
  State<MachineWorkspaceScreen> createState() => _MachineWorkspaceScreenState();
}

class _MachineWorkspaceScreenState extends State<MachineWorkspaceScreen> {
  MachineDocuments? _documents;
  String? _error;
  bool _bookmarked = false;

  @override
  void initState() {
    super.initState();
    _load();
    widget.store.addRecent(widget.machine);
    widget.store.isBookmarked(widget.machine.id).then((value) {
      if (mounted) setState(() => _bookmarked = value);
    });
  }

  Future<void> _load() async {
    setState(() {
      _documents = null;
      _error = null;
    });
    try {
      final documents = await widget.machinesApi.machineDocuments(
        widget.machine.id,
      );
      if (mounted) setState(() => _documents = documents);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  Future<void> _toggleBookmark() async {
    final bookmarked = await widget.store.toggleBookmark(widget.machine);
    if (mounted) setState(() => _bookmarked = bookmarked);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.machine.modelNumber),
        actions: [
          IconButton(
            key: const Key('bookmark-button'),
            onPressed: _toggleBookmark,
            tooltip: _bookmarked ? 'Remove bookmark' : 'Bookmark this machine',
            icon: Icon(
              _bookmarked ? Icons.bookmark : Icons.bookmark_outline,
              color: _bookmarked ? AppColors.tealLight : Colors.white,
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _MachineHeader(machine: widget.machine),
            Expanded(child: _buildBody()),
          ],
        ),
      ),
    );
  }

  Widget _buildBody() {
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.cloud_off_outlined,
                size: 48,
                color: AppColors.danger,
              ),
              const SizedBox(height: 12),
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: _load,
                icon: const Icon(Icons.refresh),
                label: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }
    final documents = _documents;
    if (documents == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (documents.categories.isEmpty) {
      return const Center(
        child: Text('No documents indexed for this machine yet.'),
      );
    }
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      children: [
        for (final category in documents.categories) ...[
          _CategoryHeader(documentType: category.documentType),
          for (final document in category.documents)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _DocumentTile(
                document: document,
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => DocumentSearchScreen(
                      document: document,
                      documentsApi: widget.documentsApi,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ],
    );
  }
}

class _MachineHeader extends StatelessWidget {
  const _MachineHeader({required this.machine});

  final MachineSummary machine;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final details = {
      machine.brand,
      machine.manufacturer,
      if (machine.machineType != null)
        machine.machineType!.replaceAll('_', ' '),
      if (machine.family != null) machine.family!,
    }.join(' · ');
    return Container(
      color: AppColors.navy,
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      child: Text(
        details,
        style: theme.textTheme.bodyMedium?.copyWith(
          color: Colors.white.withValues(alpha: 0.85),
        ),
      ),
    );
  }
}

class _CategoryHeader extends StatelessWidget {
  const _CategoryHeader({required this.documentType});

  final String documentType;

  static const _labels = {
    'service_manual': 'Manuals',
    'parts_manual': 'Parts & Exploded Diagrams',
    'wiring_diagram': 'Wiring',
    'installation_manual': 'Installation',
    'operation_manual': 'Operation',
    'programming_manual': 'Programming',
    'diagnostics': 'Diagnostics',
    'maintenance_manual': 'Maintenance',
    'technical_bulletin': 'Technical Bulletins',
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final label = _labels[documentType] ?? documentType.replaceAll('_', ' ');
    return Padding(
      padding: const EdgeInsets.only(top: 12, bottom: 8),
      child: Text(
        label,
        style: theme.textTheme.titleMedium?.copyWith(
          fontWeight: FontWeight.w700,
          color: AppColors.navy,
        ),
      ),
    );
  }
}

class _DocumentTile extends StatelessWidget {
  const _DocumentTile({required this.document, required this.onTap});

  final DocumentItem document;
  final VoidCallback onTap;

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
              Icon(
                Icons.menu_book_outlined,
                color: theme.colorScheme.primary,
                size: 26,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(document.title, style: theme.textTheme.titleSmall),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 6,
                      runSpacing: 4,
                      children: [
                        InfoBadge(document.provider),
                        if (document.revision != null)
                          InfoBadge(document.revision!),
                        if (document.publishedAt != null)
                          InfoBadge(document.publishedAt!),
                        if (document.language != null)
                          InfoBadge(document.language!.toUpperCase()),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
