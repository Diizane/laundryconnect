import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:pdfx/pdfx.dart';

import '../api/api_client.dart';
import '../models/provider_documents.dart';

/// In-app PDF reader with keyword search and a tappable table of contents
/// (Milestone 13).
///
/// Both are served by the backend from the cached document, so the phone
/// does no text extraction. Pages are rendered from bytes held in memory —
/// provider documents are never written to disk on the device.
class PdfViewerScreen extends StatefulWidget {
  const PdfViewerScreen({
    super.key,
    required this.title,
    required this.bytes,
    this.api,
    this.providerId,
    this.token,
  });

  final String title;
  final Uint8List bytes;

  /// Supplied when the document came from a provider, enabling search and
  /// contents. Omitted for documents opened without a backend reference.
  final ProviderDocumentsApi? api;
  final String? providerId;
  final String? token;

  bool get supportsNavigation =>
      api != null && providerId != null && token != null;

  @override
  State<PdfViewerScreen> createState() => _PdfViewerScreenState();
}

class _PdfViewerScreenState extends State<PdfViewerScreen> {
  late final PdfControllerPinch _controller;
  final _searchController = TextEditingController();

  DocumentContents? _contents;
  DocumentSearchResults? _results;
  bool _searching = false;
  bool _searchOpen = false;
  String? _navigationError;

  @override
  void initState() {
    super.initState();
    _controller = PdfControllerPinch(
      document: PdfDocument.openData(widget.bytes),
    );
    if (widget.supportsNavigation) _loadContents();
  }

  @override
  void dispose() {
    _controller.dispose();
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadContents() async {
    try {
      final contents = await widget.api!.documentContents(
        widget.providerId!,
        widget.token!,
      );
      if (mounted) setState(() => _contents = contents);
    } on ApiException catch (error) {
      // Navigation is an enhancement: the manual is already readable, so a
      // failure here must never obscure it.
      if (mounted) setState(() => _navigationError = error.message);
    }
  }

  Future<void> _search(String query) async {
    if (query.trim().isEmpty) return;
    setState(() => _searching = true);
    try {
      final results = await widget.api!.searchWithinDocument(
        widget.providerId!,
        widget.token!,
        query.trim(),
      );
      if (mounted) setState(() => _results = results);
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  void _goToPage(int pageNumber) {
    _controller.animateToPage(pageNumber: pageNumber);
  }

  bool get _searchAvailable => _contents?.searchable ?? false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: _searchOpen
            ? TextField(
                key: const Key('pdf-search-field'),
                controller: _searchController,
                autofocus: true,
                textInputAction: TextInputAction.search,
                style: const TextStyle(color: Colors.white),
                decoration: const InputDecoration(
                  hintText: 'Search in this document',
                  hintStyle: TextStyle(color: Colors.white70),
                  border: InputBorder.none,
                ),
                onSubmitted: _search,
              )
            : Text(widget.title, maxLines: 1, overflow: TextOverflow.ellipsis),
        actions: [
          if (widget.supportsNavigation && _searchAvailable)
            IconButton(
              key: const Key('pdf-search-toggle'),
              tooltip: _searchOpen ? 'Close search' : 'Search in document',
              icon: Icon(_searchOpen ? Icons.close : Icons.search),
              onPressed: () => setState(() {
                _searchOpen = !_searchOpen;
                if (!_searchOpen) {
                  _searchController.clear();
                  _results = null;
                }
              }),
            ),
          if (_contents?.hasContents ?? false)
            Builder(
              builder: (context) => IconButton(
                key: const Key('pdf-contents-toggle'),
                tooltip: 'Contents',
                icon: const Icon(Icons.list),
                onPressed: () => Scaffold.of(context).openEndDrawer(),
              ),
            ),
        ],
      ),
      endDrawer: (_contents?.hasContents ?? false)
          ? _ContentsDrawer(
              entries: _contents!.contents,
              onSelect: (entry) {
                Navigator.of(context).pop();
                _goToPage(entry.pageNumber);
              },
            )
          : null,
      body: Column(
        children: [
          if (_searching) const LinearProgressIndicator(minHeight: 2),
          if (widget.supportsNavigation &&
              _contents != null &&
              !_contents!.searchable)
            _Notice(
              icon: Icons.image_search,
              // Honest, not a silent empty result: some manuals embed fonts
              // without character maps, so there is no text to search.
              message:
                  'This manual has no searchable text — use the contents or '
                  'scroll to find what you need.',
            ),
          if (_navigationError != null)
            _Notice(icon: Icons.info_outline, message: _navigationError!),
          if (_results != null)
            _SearchResults(results: _results!, onGo: _goToPage),
          Expanded(
            child: PdfViewPinch(
              controller: _controller,
              builders: PdfViewPinchBuilders<DefaultBuilderOptions>(
                options: const DefaultBuilderOptions(),
                errorBuilder: (_, error) => Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      'This document could not be displayed.',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyMedium,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Notice extends StatelessWidget {
  const _Notice({required this.icon, required this.message});

  final IconData icon;
  final String message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      width: double.infinity,
      color: theme.colorScheme.secondaryContainer,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(
        children: [
          Icon(icon, size: 18, color: theme.colorScheme.onSecondaryContainer),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSecondaryContainer,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SearchResults extends StatelessWidget {
  const _SearchResults({required this.results, required this.onGo});

  final DocumentSearchResults results;
  final void Function(int pageNumber) onGo;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (results.hits.isEmpty) {
      return _Notice(
        icon: Icons.search_off,
        message: 'No matches for "${results.query}" in this document.',
      );
    }
    return SizedBox(
      height: 160,
      child: Material(
        color: theme.colorScheme.surfaceContainerHighest,
        child: ListView.builder(
          itemCount: results.hits.length,
          itemBuilder: (context, index) {
            final hit = results.hits[index];
            return ListTile(
              dense: true,
              leading: Text(
                'p${hit.pageNumber}',
                style: theme.textTheme.labelLarge?.copyWith(
                  color: theme.colorScheme.primary,
                ),
              ),
              title: Text(
                hit.snippet,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall,
              ),
              onTap: () => onGo(hit.pageNumber),
            );
          },
        ),
      ),
    );
  }
}

class _ContentsDrawer extends StatelessWidget {
  const _ContentsDrawer({required this.entries, required this.onSelect});

  final List<ContentsEntry> entries;
  final void Function(ContentsEntry entry) onSelect;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Drawer(
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: Text('Contents', style: theme.textTheme.titleMedium),
            ),
            const Divider(height: 1),
            Expanded(
              child: ListView.builder(
                itemCount: entries.length,
                itemBuilder: (context, index) {
                  final entry = entries[index];
                  return ListTile(
                    dense: true,
                    // Nested headings are indented so the structure reads.
                    contentPadding: EdgeInsets.only(
                      left: 16 + entry.depth * 16.0,
                      right: 16,
                    ),
                    title: Text(entry.title),
                    trailing: Text(
                      '${entry.pageNumber}',
                      style: theme.textTheme.labelMedium,
                    ),
                    onTap: () => onSelect(entry),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
