import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../models/document_search.dart';
import '../models/machine.dart';
import '../models/provider_documents.dart';
import '../models/search.dart';

/// Base URL for the LaundryConnect backend.
///
/// Override at build/run time:
///   flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8000
///
/// Default targets the Android emulator's host loopback. No credentials
/// live in this app — all provider access happens on the backend.
const apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);

/// API key for a secured (staging/production) backend, supplied at build
/// time: `--dart-define=API_KEY=…`. Empty for local/dev backends that run
/// without authentication.
///
/// This is an internal-distribution control, not a user credential: a key
/// inside an APK is extractable by anyone holding the file. Keep builds
/// internal and rotate the key if a device is lost. Per-technician accounts
/// are the follow-up milestone. It authenticates ONLY to the LaundryConnect
/// backend — never to a provider.
const apiKey = String.fromEnvironment('API_KEY', defaultValue: '');

/// What kind of failure occurred — lets screens choose recovery behaviour
/// (retry, rediscover, or explain) without parsing message text.
enum ApiErrorKind {
  /// The resource does not exist (or an opaque reference has expired —
  /// the backend deliberately makes those indistinguishable).
  notFound,

  /// The provider's session needs operator reauthentication (backend 503
  /// with the reauthentication detail).
  reauthenticationRequired,

  /// The provider refused or returned bad content (backend 502).
  providerFailure,

  /// The request itself was invalid (400/422).
  invalidRequest,

  /// The backend rejected this build's API key (401) — the build needs
  /// updating, not a retry.
  unauthorised,

  /// Connectivity/timeout.
  network,

  /// Anything else server-side.
  server,
}

/// Thrown for any failure talking to the backend; [message] is safe to show.
class ApiException implements Exception {
  const ApiException(this.message, {this.kind = ApiErrorKind.server});

  final String message;
  final ApiErrorKind kind;

  @override
  String toString() => message;
}

abstract interface class SearchApi {
  Future<SearchResponse> search(String query);
}

abstract interface class MachinesApi {
  Future<List<MachineSummary>> findByModelNumber(String modelNumber);

  Future<MachineDocuments> machineDocuments(String machineId);
}

abstract interface class DocumentsApi {
  Future<DocumentSearchResult> searchInDocument(
    String documentId,
    String query,
  );

  Future<DocumentPageContent> getPage(String documentId, int pageNumber);
}

/// Provider document discovery + download (Milestone 9 backend API). The
/// app only ever handles opaque backend tokens — never provider URLs.
abstract interface class ProviderDocumentsApi {
  Future<DocumentDiscovery> discoverDocuments(String providerId, String ref);

  /// Downloads one PDF via the backend proxy, reporting whether the bytes
  /// came from the provider or from the server's stored copy. Nothing is
  /// persisted by this client; callers hold the bytes in memory only.
  Future<DownloadedDocument> downloadDocument(String providerId, String token);

  /// Page count, whether the document can be searched, and its embedded
  /// contents with page numbers (Milestone 13).
  Future<DocumentContents> documentContents(String providerId, String token);

  /// Find text inside one document; hits cite the page they appear on.
  Future<DocumentSearchResults> searchWithinDocument(
    String providerId,
    String token,
    String query,
  );

  /// Assembly drawings available for a machine (Milestone 15).
  Future<List<DrawingSummary>> discoverDrawings(String providerId, String ref);

  /// One drawing's vector diagram and parts list.
  Future<DrawingDetail> fetchDrawing(String providerId, String token);
}

/// Shared request plumbing: timeouts, connectivity errors, status handling,
/// and JSON decoding with technician-friendly messages.
class _BackendClient {
  _BackendClient({http.Client? client, required this.baseUrl})
    : _client = client ?? http.Client();

  final http.Client _client;
  final String baseUrl;

  static const _timeout = Duration(seconds: 15);

  Future<http.Response> _send(
    String method,
    String path, {
    Map<String, String>? queryParameters,
    Object? body,
    Duration? timeout,
  }) async {
    final uri = Uri.parse(
      '$baseUrl$path',
    ).replace(queryParameters: queryParameters);
    try {
      final request = http.Request(method, uri);
      if (apiKey.isNotEmpty) request.headers['X-API-Key'] = apiKey;
      if (body != null) {
        request.headers['Content-Type'] = 'application/json';
        request.body = jsonEncode(body);
      }
      final streamed = await _client.send(request).timeout(timeout ?? _timeout);
      return await http.Response.fromStream(streamed);
    } on TimeoutException {
      throw const ApiException(
        'Request timed out. Check your connection and try again.',
        kind: ApiErrorKind.network,
      );
    } on SocketException {
      throw const ApiException(
        'Cannot reach the server. Check your connection.',
        kind: ApiErrorKind.network,
      );
    } on http.ClientException {
      throw const ApiException(
        'Cannot reach the server. Check your connection.',
        kind: ApiErrorKind.network,
      );
    }
  }

  /// The backend's structured error envelope message, if present.
  String? _errorMessage(http.Response response) {
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      final error = (decoded as Map<String, dynamic>)['error'];
      return (error as Map<String, dynamic>)['message'] as String?;
    } on Object {
      return null;
    }
  }

  Never _throwForStatus(http.Response response) {
    final detail = _errorMessage(response);
    switch (response.statusCode) {
      case 400:
        throw ApiException(
          detail ?? 'That request is not valid.',
          kind: ApiErrorKind.invalidRequest,
        );
      case 404:
        throw ApiException(detail ?? 'Not found.', kind: ApiErrorKind.notFound);
      case 401:
        throw const ApiException(
          'This app is not authorised for that server. Reinstall the current '
          'internal build.',
          kind: ApiErrorKind.unauthorised,
        );
      case 422:
        throw const ApiException(
          'That request is not valid. Try a model, part, or fault code.',
          kind: ApiErrorKind.invalidRequest,
        );
      case 502:
        throw ApiException(
          detail ?? 'The provider could not complete that request.',
          kind: ApiErrorKind.providerFailure,
        );
      case 503:
        final isReauth =
            detail != null && detail.toLowerCase().contains('reauthentication');
        throw ApiException(
          isReauth
              ? 'The Alliance session needs to be signed in again by an '
                    'operator. Try again once that is done.'
              : (detail ??
                    'The server is not fully available right now. '
                        'Try again shortly.'),
          kind: isReauth
              ? ApiErrorKind.reauthenticationRequired
              : ApiErrorKind.server,
        );
      default:
        throw ApiException(
          'Server error (${response.statusCode}). Try again shortly.',
          kind: ApiErrorKind.server,
        );
    }
  }

  Future<dynamic> requestJson(
    String method,
    String path, {
    Map<String, String>? queryParameters,
    Object? body,
  }) async {
    final response = await _send(
      method,
      path,
      queryParameters: queryParameters,
      body: body,
    );
    if (response.statusCode != 200) _throwForStatus(response);
    try {
      return jsonDecode(utf8.decode(response.bodyBytes));
    } on FormatException {
      throw const ApiException('Unexpected server response.');
    }
  }

  /// Fetch binary content (the PDF proxy). Verifies the declared content
  /// type so an unexpected body is never handed to a viewer.
  Future<({Uint8List bytes, Map<String, String> headers})> requestBytes(
    String path, {
    required String expectedContentType,
    Duration? timeout,
  }) async {
    final response = await _send('GET', path, timeout: timeout);
    if (response.statusCode != 200) _throwForStatus(response);
    final contentType =
        response.headers['content-type']?.split(';').first.trim() ?? '';
    if (contentType != expectedContentType) {
      throw const ApiException(
        'Unexpected server response.',
        kind: ApiErrorKind.providerFailure,
      );
    }
    return (bytes: response.bodyBytes, headers: response.headers);
  }
}

class HttpSearchApi implements SearchApi {
  HttpSearchApi({http.Client? client, String baseUrl = apiBaseUrl})
    : _backend = _BackendClient(client: client, baseUrl: baseUrl);

  final _BackendClient _backend;

  @override
  Future<SearchResponse> search(String query) async {
    final json = await _backend.requestJson(
      'POST',
      '/api/v1/search',
      body: {'query': query},
    );
    try {
      return SearchResponse.fromJson(json as Map<String, dynamic>);
    } on TypeError {
      throw const ApiException('Unexpected server response.');
    }
  }
}

class HttpDocumentsApi implements DocumentsApi {
  HttpDocumentsApi({http.Client? client, String baseUrl = apiBaseUrl})
    : _backend = _BackendClient(client: client, baseUrl: baseUrl);

  final _BackendClient _backend;

  @override
  Future<DocumentSearchResult> searchInDocument(
    String documentId,
    String query,
  ) async {
    final json = await _backend.requestJson(
      'GET',
      '/api/v1/documents/$documentId/search',
      queryParameters: {'q': query},
    );
    try {
      return DocumentSearchResult.fromJson(json as Map<String, dynamic>);
    } on TypeError {
      throw const ApiException('Unexpected server response.');
    }
  }

  @override
  Future<DocumentPageContent> getPage(String documentId, int pageNumber) async {
    final json = await _backend.requestJson(
      'GET',
      '/api/v1/documents/$documentId/pages/$pageNumber',
    );
    try {
      return DocumentPageContent.fromJson(json as Map<String, dynamic>);
    } on TypeError {
      throw const ApiException('Unexpected server response.');
    }
  }
}

class HttpProviderDocumentsApi implements ProviderDocumentsApi {
  HttpProviderDocumentsApi({http.Client? client, String baseUrl = apiBaseUrl})
    : _backend = _BackendClient(client: client, baseUrl: baseUrl);

  final _BackendClient _backend;

  /// PDFs can be larger than JSON responses; allow a longer window.
  static const _downloadTimeout = Duration(seconds: 90);

  @override
  Future<DocumentDiscovery> discoverDocuments(
    String providerId,
    String ref,
  ) async {
    final json = await _backend.requestJson(
      'GET',
      '/api/v1/providers/$providerId/documents',
      queryParameters: {'ref': ref},
    );
    try {
      return DocumentDiscovery.fromJson(json as Map<String, dynamic>);
    } on TypeError {
      throw const ApiException('Unexpected server response.');
    }
  }

  @override
  Future<DownloadedDocument> downloadDocument(
    String providerId,
    String token,
  ) async {
    final response = await _backend.requestBytes(
      '/api/v1/providers/$providerId/documents/$token',
      expectedContentType: 'application/pdf',
      timeout: _downloadTimeout,
    );
    return DownloadedDocument(
      bytes: response.bytes,
      // Absent headers mean an older backend: treat as live rather than
      // inventing staleness.
      origin: response.headers['x-document-origin'] ?? 'live',
      ageSeconds:
          int.tryParse(response.headers['x-document-age-seconds'] ?? '') ?? 0,
    );
  }

  @override
  Future<DocumentContents> documentContents(
    String providerId,
    String token,
  ) async {
    final json = await _backend.requestJson(
      'GET',
      '/api/v1/providers/$providerId/documents/$token/contents',
    );
    try {
      return DocumentContents.fromJson(json as Map<String, dynamic>);
    } on TypeError {
      throw const ApiException('Unexpected server response.');
    }
  }

  @override
  Future<DocumentSearchResults> searchWithinDocument(
    String providerId,
    String token,
    String query,
  ) async {
    final json = await _backend.requestJson(
      'GET',
      '/api/v1/providers/$providerId/documents/$token/search',
      queryParameters: {'q': query},
    );
    try {
      return DocumentSearchResults.fromJson(json as Map<String, dynamic>);
    } on TypeError {
      throw const ApiException('Unexpected server response.');
    }
  }

  @override
  Future<List<DrawingSummary>> discoverDrawings(
    String providerId,
    String ref,
  ) async {
    final json = await _backend.requestJson(
      'GET',
      '/api/v1/providers/$providerId/drawings',
      queryParameters: {'ref': ref},
    );
    try {
      return ((json as Map<String, dynamic>)['drawings'] as List<dynamic>)
          .map((d) => DrawingSummary.fromJson(d as Map<String, dynamic>))
          .toList();
    } on TypeError {
      throw const ApiException('Unexpected server response.');
    }
  }

  @override
  Future<DrawingDetail> fetchDrawing(String providerId, String token) async {
    final json = await _backend.requestJson(
      'GET',
      // Diagrams are large; allow the same window as a document download.
      '/api/v1/providers/$providerId/drawings/$token',
    );
    try {
      return DrawingDetail.fromJson(json as Map<String, dynamic>);
    } on TypeError {
      throw const ApiException('Unexpected server response.');
    }
  }
}

class HttpMachinesApi implements MachinesApi {
  HttpMachinesApi({http.Client? client, String baseUrl = apiBaseUrl})
    : _backend = _BackendClient(client: client, baseUrl: baseUrl);

  final _BackendClient _backend;

  @override
  Future<List<MachineSummary>> findByModelNumber(String modelNumber) async {
    final json = await _backend.requestJson(
      'GET',
      '/api/v1/machines',
      queryParameters: {'model_number': modelNumber},
    );
    try {
      return (json as List<dynamic>)
          .map((m) => MachineSummary.fromJson(m as Map<String, dynamic>))
          .toList();
    } on TypeError {
      throw const ApiException('Unexpected server response.');
    }
  }

  @override
  Future<MachineDocuments> machineDocuments(String machineId) async {
    final json = await _backend.requestJson(
      'GET',
      '/api/v1/machines/$machineId/documents',
    );
    try {
      return MachineDocuments.fromJson(json as Map<String, dynamic>);
    } on TypeError {
      throw const ApiException('Unexpected server response.');
    }
  }
}
