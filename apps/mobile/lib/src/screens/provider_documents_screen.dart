import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../models/provider_documents.dart';
import '../models/search.dart';
import '../widgets/badges.dart';
import 'pdf_viewer_screen.dart';

/// Called when a document has been downloaded and should be shown. Default
/// pushes the in-app PDF viewer; tests inject a fake.
typedef PdfOpener =
    Future<void> Function(BuildContext context, String title, Uint8List bytes);

Future<void> _openInAppViewer(
  BuildContext context,
  String title,
  Uint8List bytes,
) {
  return Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => PdfViewerScreen(title: title, bytes: bytes),
    ),
  );
}

/// Documents a provider offers for one search result: discover → pick →
/// download via the backend proxy → read. The app only ever handles opaque
/// backend tokens; provider URLs never exist on this side.
class ProviderDocumentsScreen extends StatefulWidget {
  const ProviderDocumentsScreen({
    super.key,
    required this.result,
    required this.api,
    this.openPdf = _openInAppViewer,
  });

  final SearchResult result;
  final ProviderDocumentsApi api;
  final PdfOpener openPdf;

  @override
  State<ProviderDocumentsScreen> createState() =>
      _ProviderDocumentsScreenState();
}

sealed class _DocsState {
  const _DocsState();
}

class _Loading extends _DocsState {
  const _Loading();
}

class _Failed extends _DocsState {
  const _Failed(this.message, {this.reauthRequired = false});

  final String message;
  final bool reauthRequired;
}

class _Loaded extends _DocsState {
  const _Loaded(this.discovery);

  final DocumentDiscovery discovery;
}

class _ProviderDocumentsScreenState extends State<ProviderDocumentsScreen> {
  _DocsState _state = const _Loading();

  /// Title of the document currently downloading (one at a time), if any.
  String? _downloading;

  @override
  void initState() {
    super.initState();
    _discover();
  }

  Future<void> _discover() async {
    setState(() => _state = const _Loading());
    try {
      final ref = widget.result.documentRef;
      if (ref == null) {
        throw const ApiException(
          'This result has no document reference.',
          kind: ApiErrorKind.invalidRequest,
        );
      }
      final discovery = await widget.api.discoverDocuments(
        widget.result.providerId,
        ref,
      );
      if (!mounted) return;
      setState(() => _state = _Loaded(discovery));
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(
        () => _state = _Failed(
          error.message,
          reauthRequired: error.kind == ApiErrorKind.reauthenticationRequired,
        ),
      );
    }
  }

  Future<void> _open(ProviderDocument document) async {
    final token = document.token;
    if (token == null || _downloading != null) return;
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _downloading = document.title);
    try {
      Uint8List bytes;
      try {
        bytes = await widget.api.downloadDocument(
          widget.result.providerId,
          token,
        );
      } on ApiException catch (error) {
        // A 404 here usually means the short-lived token expired while the
        // technician was reading the list: rediscover once for a fresh
        // token and retry, rather than surfacing token mechanics.
        if (error.kind != ApiErrorKind.notFound) rethrow;
        final fresh = await _rediscoverToken(document);
        if (fresh == null) {
          throw const ApiException(
            'That document is no longer available.',
            kind: ApiErrorKind.notFound,
          );
        }
        bytes = await widget.api.downloadDocument(
          widget.result.providerId,
          fresh,
        );
      }
      if (!mounted) return;
      await widget.openPdf(context, document.title, bytes);
    } on ApiException catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.message)));
    } finally {
      if (mounted) setState(() => _downloading = null);
    }
  }

  /// Refresh the discovery (also updating the list) and return the fresh
  /// token for the same document, matched by its stable identity.
  Future<String?> _rediscoverToken(ProviderDocument document) async {
    final ref = widget.result.documentRef;
    if (ref == null) return null;
    final discovery = await widget.api.discoverDocuments(
      widget.result.providerId,
      ref,
    );
    if (mounted) setState(() => _state = _Loaded(discovery));
    for (final candidate in discovery.documents) {
      if (candidate.title == document.title &&
          candidate.partNumber == document.partNumber &&
          candidate.token != null) {
        return candidate.token;
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.result.model ?? widget.result.title,
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
                OutlinedButton(
                  onPressed: _discover,
                  child: const Text('Retry'),
                ),
              ],
            ),
          ),
        ),
        _Loaded(:final discovery) when discovery.documents.isEmpty => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(
              'No documents listed for this machine.',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium,
            ),
          ),
        ),
        _Loaded(:final discovery) => ListView.builder(
          itemCount: discovery.documents.length,
          itemBuilder: (context, index) {
            final document = discovery.documents[index];
            final downloading = _downloading == document.title;
            return ListTile(
              enabled: document.isDownloadable,
              leading: Icon(
                document.isDownloadable
                    ? Icons.picture_as_pdf_outlined
                    : Icons.block,
                color: document.isDownloadable
                    ? theme.colorScheme.primary
                    : theme.disabledColor,
              ),
              title: Text(document.title),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (document.comment != null) Text(document.comment!),
                  const SizedBox(height: 4),
                  Wrap(
                    spacing: 6,
                    runSpacing: 4,
                    children: [
                      DataOriginBadge(document.dataOrigin),
                      if (document.documentType != null)
                        InfoBadge(document.documentType!),
                      if (document.partNumber != null)
                        InfoBadge(document.partNumber!),
                      if (document.category != null)
                        InfoBadge(document.category!),
                      if (document.languages.isNotEmpty)
                        InfoBadge(document.languages.join(', ')),
                      if (!document.isDownloadable)
                        const InfoBadge('not downloadable'),
                    ],
                  ),
                ],
              ),
              trailing: downloading
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : null,
              onTap: document.isDownloadable ? () => _open(document) : null,
            );
          },
        ),
      },
    );
  }
}
