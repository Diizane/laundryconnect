import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

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

class HttpSearchApi implements SearchApi {
  HttpSearchApi({http.Client? client, this.baseUrl = apiBaseUrl})
    : _client = client ?? http.Client();

  final http.Client _client;
  final String baseUrl;

  static const _timeout = Duration(seconds: 15);

  @override
  Future<SearchResponse> search(String query) async {
    final http.Response response;
    try {
      response = await _client
          .post(
            Uri.parse('$baseUrl/api/v1/search'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'query': query}),
          )
          .timeout(_timeout);
    } on TimeoutException {
      throw const ApiException(
        'Search timed out. Check your connection and try again.',
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

    if (response.statusCode == 422) {
      throw const ApiException(
        'That search is not valid. Try a model, part, or fault code.',
      );
    }
    if (response.statusCode != 200) {
      throw ApiException(
        'Server error (${response.statusCode}). Try again shortly.',
      );
    }
    try {
      return SearchResponse.fromJson(
        jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>,
      );
    } on FormatException {
      throw const ApiException('Unexpected server response.');
    } on TypeError {
      throw const ApiException('Unexpected server response.');
    }
  }
}
