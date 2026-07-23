import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:laundryconnect/src/api/api_client.dart';
import 'package:laundryconnect/src/app.dart';
import 'package:laundryconnect/src/models/search.dart';

SearchResult _result({
  String title = 'SC60 Service Manual (sample)',
  String dataOrigin = 'mock',
}) => SearchResult(
  providerId: 'mock',
  sourceReference: 'ref-1',
  resultType: 'document',
  dataOrigin: dataOrigin,
  title: title,
  documentType: 'service_manual',
  model: 'SC60',
  manufacturer: 'Alliance Laundry Systems',
  brand: 'Speed Queen',
);

SearchResponse _response({int total = 1, List<ProviderOutcome>? providers}) =>
    SearchResponse(
      query: 'SC60',
      detectedQueryType: 'model',
      totalResults: total,
      groups: total == 0
          ? []
          : [
              MachineGroup(
                manufacturer: 'Alliance Laundry Systems',
                brand: 'Speed Queen',
                model: 'SC60',
                results: [_result()],
              ),
            ],
      providers:
          providers ??
          [
            const ProviderOutcome(
              providerId: 'mock',
              status: 'success',
              resultCount: 1,
            ),
          ],
    );

class FakeSearchApi implements SearchApi {
  FakeSearchApi(this._handler);

  final Future<SearchResponse> Function(String query) _handler;
  final queries = <String>[];

  @override
  Future<SearchResponse> search(String query) {
    queries.add(query);
    return _handler(query);
  }
}

Future<void> _pumpAppAndSearch(WidgetTester tester, SearchApi api) async {
  await tester.pumpWidget(LaundryConnectApp(searchApi: api));
  await tester.enterText(find.byType(TextField), 'SC60');
  await tester.tap(find.byKey(const Key('search-button')));
}

void main() {
  testWidgets('initial state shows search field and hint', (tester) async {
    await tester.pumpWidget(
      LaundryConnectApp(searchApi: FakeSearchApi((_) async => _response())),
    );

    expect(find.text('LaundryConnect'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
    expect(find.textContaining('Model, serial, part number'), findsOneWidget);
    expect(find.textContaining('Search manuals, parts'), findsOneWidget);
  });

  testWidgets('shows loading indicator while searching', (tester) async {
    final completer = Completer<SearchResponse>();
    await _pumpAppAndSearch(tester, FakeSearchApi((_) => completer.future));
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    completer.complete(_response());
    await tester.pumpAndSettle();
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('renders grouped results with data-origin and provider badges', (
    tester,
  ) async {
    final api = FakeSearchApi((_) async => _response());
    await _pumpAppAndSearch(tester, api);
    await tester.pumpAndSettle();

    expect(api.queries, ['SC60']);
    expect(find.text('SC60'), findsWidgets); // group header
    expect(find.text('SC60 Service Manual (sample)'), findsOneWidget);
    expect(find.text('MOCK'), findsOneWidget); // origin badge, never hidden
    expect(find.text('mock'), findsOneWidget); // provider badge
  });

  testWidgets('shows empty state for zero results', (tester) async {
    await _pumpAppAndSearch(
      tester,
      FakeSearchApi((_) async => _response(total: 0)),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('No results for "SC60"'), findsOneWidget);
  });

  testWidgets('shows error state with retry that searches again', (
    tester,
  ) async {
    var calls = 0;
    final api = FakeSearchApi((_) async {
      calls++;
      if (calls == 1) throw const ApiException('Cannot reach the server.');
      return _response();
    });

    await _pumpAppAndSearch(tester, api);
    await tester.pumpAndSettle();
    expect(find.text('Cannot reach the server.'), findsOneWidget);

    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    expect(find.text('SC60 Service Manual (sample)'), findsOneWidget);
    expect(calls, 2);
  });

  testWidgets('shows partial-failure banner when a provider degrades', (
    tester,
  ) async {
    final api = FakeSearchApi(
      (_) async => _response(
        providers: [
          const ProviderOutcome(
            providerId: 'mock',
            status: 'success',
            resultCount: 1,
          ),
          const ProviderOutcome(providerId: 'alliance', status: 'timed_out'),
        ],
      ),
    );
    await _pumpAppAndSearch(tester, api);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('partial-failure-banner')), findsOneWidget);
    expect(find.textContaining('alliance'), findsOneWidget);
    // Results still shown despite the degraded provider.
    expect(find.text('SC60 Service Manual (sample)'), findsOneWidget);
  });

  testWidgets('blank query does not trigger a search', (tester) async {
    final api = FakeSearchApi((_) async => _response());
    await tester.pumpWidget(LaundryConnectApp(searchApi: api));
    await tester.tap(find.byKey(const Key('search-button')));
    await tester.pumpAndSettle();

    expect(api.queries, isEmpty);
    expect(find.textContaining('Search manuals, parts'), findsOneWidget);
  });
}
