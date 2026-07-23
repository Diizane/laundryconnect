import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../models/document_search.dart';
import '../models/machine.dart';
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

/// Thrown for any failure talking to the backend; [message] is safe to show.
class ApiException implements Exception {
  const ApiException(this.message);

  final String message;

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

/// Shared request plumbing: timeouts, connectivity errors, status handling,
/// and JSON decoding with technician-friendly messages.
class _BackendClient {
  _BackendClient({http.Client? client, required this.baseUrl})
    : _client = client ?? http.Client();

  final http.Client _client;
  final String baseUrl;

  static const _timeout = Duration(seconds: 15);

  Future<dynamic> requestJson(
    String method,
    String path, {
    Map<String, String>? queryParameters,
    Object? body,
  }) async {
    final uri = Uri.parse(
      '$baseUrl$path',
    ).replace(queryParameters: queryParameters);
    final http.Response response;
    try {
      final request = http.Request(method, uri);
      if (body != null) {
        request.headers['Content-Type'] = 'application/json';
        request.body = jsonEncode(body);
      }
      final streamed = await _client.send(request).timeout(_timeout);
      response = await http.Response.fromStream(streamed);
    } on TimeoutException {
      throw const ApiException(
        'Request timed out. Check your connection and try again.',
      );
    } on SocketException {
      throw const ApiException(
        'Cannot reach the server. Check your connection.',
      );
    } on http.ClientException {
      throw const ApiException(
        'Cannot reach the server. Check your connection.',
      );
    }

    switch (response.statusCode) {
      case 200:
        break;
      case 404:
        throw const ApiException('Not found.');
      case 422:
        throw const ApiException(
          'That request is not valid. Try a model, part, or fault code.',
        );
      case 503:
        throw const ApiException(
          'The server is not fully available right now. Try again shortly.',
        );
      default:
        throw ApiException(
          'Server error (${response.statusCode}). Try again shortly.',
        );
    }

    try {
      return jsonDecode(utf8.decode(response.bodyBytes));
    } on FormatException {
      throw const ApiException('Unexpected server response.');
    }
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
