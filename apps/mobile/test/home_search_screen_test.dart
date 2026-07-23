import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:laundryconnect/src/api/api_client.dart';
import 'package:laundryconnect/src/app.dart';
import 'package:laundryconnect/src/models/search.dart';

import 'fakes.dart';

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

Widget _app(
  SearchApi searchApi, {
  FakeMachinesApi? machinesApi,
  FakeWorkspaceStore? store,
}) => LaundryConnectApp(
  searchApi: searchApi,
  machinesApi: machinesApi ?? FakeMachinesApi(),
  documentsApi: FakeDocumentsApi(),
  store: store ?? FakeWorkspaceStore(),
);

Future<void> _pumpAppAndSearch(WidgetTester tester, Widget app) async {
  await tester.pumpWidget(app);
  await tester.enterText(find.byType(TextField), 'SC60');
  await tester.tap(find.byKey(const Key('search-button')));
}

void main() {
  testWidgets('initial state shows search field and hint', (tester) async {
    await tester.pumpWidget(_app(FakeSearchApi((_) async => _response())));
    await tester.pumpAndSettle();

    expect(find.text('LaundryConnect'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
    expect(find.textContaining('Model, serial, part number'), findsOneWidget);
    expect(find.textContaining('Search manuals, parts'), findsOneWidget);
  });

  testWidgets('idle state lists bookmarked and recent machines', (
    tester,
  ) async {
    final store = FakeWorkspaceStore()
      ..recents.add(sc60)
      ..bookmarks.add(sc60);
    await tester.pumpWidget(
      _app(FakeSearchApi((_) async => _response()), store: store),
    );
    await tester.pumpAndSettle();

    expect(find.text('Bookmarked machines'), findsOneWidget);
    expect(find.text('Recent machines'), findsOneWidget);
    expect(find.text('SC60 · Speed Queen'), findsNWidgets(2));
  });

  testWidgets('tapping a recent machine opens its workspace', (tester) async {
    final store = FakeWorkspaceStore()..recents.add(sc60);
    await tester.pumpWidget(
      _app(FakeSearchApi((_) async => _response()), store: store),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('SC60 · Speed Queen'));
    await tester.pumpAndSettle();

    expect(find.text('Manuals'), findsOneWidget); // workspace category
    expect(find.text('SC60 Service Manual (sample)'), findsOneWidget);
  });

  testWidgets('shows loading indicator while searching', (tester) async {
    final completer = Completer<SearchResponse>();
    await _pumpAppAndSearch(
      tester,
      _app(FakeSearchApi((_) => completer.future)),
    );
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
    await _pumpAppAndSearch(tester, _app(api));
    await tester.pumpAndSettle();

    expect(api.queries, ['SC60']);
    expect(find.text('SC60'), findsWidgets); // group header
    expect(find.text('SC60 Service Manual (sample)'), findsOneWidget);
    expect(find.text('MOCK'), findsOneWidget); // origin badge, never hidden
    expect(find.text('mock'), findsOneWidget); // provider badge
  });

  testWidgets('tapping a search result opens the machine workspace', (
    tester,
  ) async {
    final store = FakeWorkspaceStore();
    await _pumpAppAndSearch(
      tester,
      _app(FakeSearchApi((_) async => _response()), store: store),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('SC60 Service Manual (sample)'));
    await tester.pumpAndSettle();

    expect(find.text('Manuals'), findsOneWidget);
    expect(find.text('Wiring'), findsOneWidget);
    expect(store.recents.map((m) => m.id), ['machine-1']);
  });

  testWidgets('unknown model shows a snackbar instead of a workspace', (
    tester,
  ) async {
    await _pumpAppAndSearch(
      tester,
      _app(
        FakeSearchApi((_) async => _response()),
        machinesApi: FakeMachinesApi(machines: const []),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('SC60 Service Manual (sample)'));
    await tester.pumpAndSettle();

    expect(find.text('No workspace available for SC60 yet.'), findsOneWidget);
    expect(find.text('Manuals'), findsNothing);
  });

  testWidgets('shows empty state for zero results', (tester) async {
    await _pumpAppAndSearch(
      tester,
      _app(FakeSearchApi((_) async => _response(total: 0))),
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

    await _pumpAppAndSearch(tester, _app(api));
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
    await _pumpAppAndSearch(tester, _app(api));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('partial-failure-banner')), findsOneWidget);
    expect(find.textContaining('alliance'), findsOneWidget);
    // Results still shown despite the degraded provider.
    expect(find.text('SC60 Service Manual (sample)'), findsOneWidget);
  });

  testWidgets('blank query does not trigger a search', (tester) async {
    final api = FakeSearchApi((_) async => _response());
    await tester.pumpWidget(_app(api));
    await tester.tap(find.byKey(const Key('search-button')));
    await tester.pumpAndSettle();

    expect(api.queries, isEmpty);
    expect(find.textContaining('Search manuals, parts'), findsOneWidget);
  });
}
