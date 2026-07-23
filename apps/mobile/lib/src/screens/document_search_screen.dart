import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../models/document_search.dart';
import '../models/machine.dart';
import '../theme/app_theme.dart';
import '../widgets/badges.dart';

/// In-document search: find the right page of a manual fast. Every hit
/// cites its page number and opens the page's extracted text.
class DocumentSearchScreen extends StatefulWidget {
  const DocumentSearchScreen({
    super.key,
    required this.document,
    required this.documentsApi,
  });

  final DocumentItem document;
  final DocumentsApi documentsApi;

  @override
  State<DocumentSearchScreen> createState() => _DocumentSearchScreenState();
}

class _DocumentSearchScreenState extends State<DocumentSearchScreen> {
  final _controller = TextEditingController();
  DocumentSearchResult? _result;
  String? _error;
  bool _loading = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _search() async {
    final query = _controller.text.trim();
    if (query.length < 2) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await widget.documentsApi.searchInDocument(
        widget.document.id,
        query,
      );
      if (mounted) {
        setState(() {
          _result = result;
          _loading = false;
        });
      }
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _error = error.message;
          _loading = false;
        });
      }
    }
  }

  void _openPage(int pageNumber) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => DocumentPageScreen(
          document: widget.document,
          documentsApi: widget.documentsApi,
          initialPage: pageNumber,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.document.title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: TextField(
                controller: _controller,
                textInputAction: TextInputAction.search,
                onSubmitted: (_) => _search(),
                decoration: InputDecoration(
                  hintText: 'Search inside this document…',
                  prefixIcon: const Icon(Icons.manage_search),
                  suffixIcon: IconButton(
                    key: const Key('doc-search-button'),
                    icon: const Icon(Icons.arrow_forward),
                    onPressed: _search,
                    tooltip: 'Search document',
                  ),
                ),
              ),
            ),
            Expanded(child: _buildBody()),
          ],
        ),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
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
                onPressed: _search,
                icon: const Icon(Icons.refresh),
                label: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }
    final result = _result;
    if (result == null) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text(
            'Search for a fault code, part number, or keyword\n'
            'to jump to the right page.',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    if (result.totalHits == 0) {
      return Center(child: Text('No pages match "${result.query}".'));
    }
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      itemCount: result.hits.length,
      itemBuilder: (context, index) {
        final hit = result.hits[index];
        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Card(
            child: InkWell(
              onTap: () => _openPage(hit.pageNumber),
              borderRadius: BorderRadius.circular(12),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        InfoBadge('Page ${hit.pageNumber}'),
                        const SizedBox(width: 6),
                        InfoBadge(hit.provider),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(hit.snippet),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

/// Extracted-text page view with previous/next navigation. The original
/// source document remains the authority; this shows its indexed text.
class DocumentPageScreen extends StatefulWidget {
  const DocumentPageScreen({
    super.key,
    required this.document,
    required this.documentsApi,
    required this.initialPage,
  });

  final DocumentItem document;
  final DocumentsApi documentsApi;
  final int initialPage;

  @override
  State<DocumentPageScreen> createState() => _DocumentPageScreenState();
}

class _DocumentPageScreenState extends State<DocumentPageScreen> {
  late int _pageNumber = widget.initialPage;
  DocumentPageContent? _content;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _content = null;
      _error = null;
    });
    try {
      final content = await widget.documentsApi.getPage(
        widget.document.id,
        _pageNumber,
      );
      if (mounted) setState(() => _content = content);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  void _goTo(int pageNumber) {
    if (pageNumber < 1) return;
    setState(() => _pageNumber = pageNumber);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Page $_pageNumber')),
      bottomNavigationBar: BottomAppBar(
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            IconButton(
              key: const Key('prev-page'),
              onPressed: _pageNumber > 1 ? () => _goTo(_pageNumber - 1) : null,
              icon: const Icon(Icons.chevron_left),
              tooltip: 'Previous page',
            ),
            Text(
              widget.document.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodySmall,
            ),
            IconButton(
              key: const Key('next-page'),
              onPressed: () => _goTo(_pageNumber + 1),
              icon: const Icon(Icons.chevron_right),
              tooltip: 'Next page',
            ),
          ],
        ),
      ),
      body: SafeArea(child: _buildBody()),
    );
  }

  Widget _buildBody() {
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Text(_error!, textAlign: TextAlign.center),
        ),
      );
    }
    final content = _content;
    if (content == null) {
      return const Center(child: CircularProgressIndicator());
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              DataOriginBadge(content.textSource),
              const SizedBox(width: 6),
              InfoBadge(widget.document.provider),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            content.textContent,
            style: const TextStyle(fontSize: 15, height: 1.5),
          ),
        ],
      ),
    );
  }
}
