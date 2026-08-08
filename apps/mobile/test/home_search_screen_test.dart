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
  FakeProviderDocumentsApi? providerDocumentsApi,
}) => LaundryConnectApp(
  searchApi: searchApi,
  machinesApi: machinesApi ?? FakeMachinesApi(),
  documentsApi: FakeDocumentsApi(),
  providerDocumentsApi: providerDocumentsApi ?? FakeProviderDocumentsApi(),
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
    // Data that is not live stays labelled; the provider chip does not.
    expect(find.text('MOCK'), findsOneWidget);
    expect(find.text('mock'), findsNothing);
  });

  testWidgets('tapping a result opens its provider documents', (tester) async {
    await _pumpAppAndSearch(
      tester,
      _app(FakeSearchApi((_) async => _response())),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('SC60 Service Manual (sample)'));
    await tester.pumpAndSettle();

    // The documents screen groups by type; the group header is what shows.
    expect(find.text('Technical Mnl'), findsOneWidget);
  });

  testWidgets('a result with no documents anywhere says so', (tester) async {
    // No provider reference and no catalog row: there is nothing to open,
    // and saying that beats a screen with nothing on it.
    final api = FakeSearchApi(
      (_) async => SearchResponse(
        query: 'SC60',
        detectedQueryType: 'model',
        totalResults: 1,
        groups: [
          MachineGroup(
            model: 'SC60',
            results: const [
              SearchResult(
                providerId: 'other',
                sourceReference: 'ref-9',
                resultType: 'document',
                dataOrigin: 'mock',
                title: 'Orphan result',
                model: 'SC60',
              ),
            ],
          ),
        ],
        providers: const [
          ProviderOutcome(
            providerId: 'other',
            status: 'success',
            resultCount: 1,
          ),
        ],
      ),
    );
    await _pumpAppAndSearch(
      tester,
      _app(api, machinesApi: FakeMachinesApi(machines: const [])),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Orphan result'));
    await tester.pumpAndSettle();

    expect(find.text('No documents listed for SC60 yet.'), findsOneWidget);
  });

  group('opening a machine from a serial search', () {
    /// What a serial search actually returns: a machine with a provider
    /// document reference, and no row in the internal catalog.
    SearchResult machine() => const SearchResult(
      providerId: 'alliance',
      sourceReference: 'als-model-430362',
      resultType: 'model',
      dataOrigin: 'live',
      title: 'IAY135J',
      model: 'IAY135J',
      documentType: 'assembly_drawings',
      metadata: {
        'manual_id': '16774',
        'model_id': '430362',
        'generation_match': 'exact',
      },
    );

    SearchResponse response() => SearchResponse(
      query: '135RX009281WK',
      detectedQueryType: 'serial',
      totalResults: 1,
      groups: [
        MachineGroup(model: 'IAY135J', results: [machine()]),
      ],
      providers: const [
        ProviderOutcome(
          providerId: 'alliance',
          status: 'success',
          resultCount: 1,
        ),
      ],
    );

    testWidgets('goes straight to the documents, not the catalog', (
      tester,
    ) async {
      // Tapping used to look the machine up in the internal catalog, which
      // the deployed backend does not run — the technician got "Database is
      // not configured." instead of their manuals.
      final machinesApi = FakeMachinesApi();
      await _pumpAppAndSearch(
        tester,
        _app(FakeSearchApi((_) async => response()), machinesApi: machinesApi),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('IAY135J').last);
      await tester.pumpAndSettle();

      expect(machinesApi.findCalls, isEmpty);
      // The documents screen groups by type; the group header is what shows.
      expect(find.text('Technical Mnl'), findsOneWidget);
    });

    testWidgets('a missing catalog is never reported as a database fault', (
      tester,
    ) async {
      final api = FakeSearchApi(
        (_) async => SearchResponse(
          query: 'SC60',
          detectedQueryType: 'model',
          totalResults: 1,
          groups: [
            MachineGroup(
              model: 'SC60',
              results: const [
                SearchResult(
                  providerId: 'other',
                  sourceReference: 'ref-9',
                  resultType: 'document',
                  dataOrigin: 'mock',
                  title: 'Orphan result',
                  model: 'SC60',
                ),
              ],
            ),
          ],
          providers: const [
            ProviderOutcome(
              providerId: 'other',
              status: 'success',
              resultCount: 1,
            ),
          ],
        ),
      );
      await _pumpAppAndSearch(
        tester,
        _app(
          api,
          machinesApi: FakeMachinesApi(
            findError: const ApiException(
              'Database is not configured.',
              kind: ApiErrorKind.unavailable,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Orphan result'));
      await tester.pumpAndSettle();

      expect(find.textContaining('Database'), findsNothing);
      expect(find.text('No documents listed for SC60 yet.'), findsOneWidget);
    });

    testWidgets('a machine card shows the serial match and nothing else', (
      tester,
    ) async {
      await _pumpAppAndSearch(
        tester,
        _app(FakeSearchApi((_) async => response())),
      );
      await tester.pumpAndSettle();

      expect(find.text('matches this serial'), findsOneWidget);
      // Chips that told a technician standing at the machine nothing.
      expect(find.text('LIVE'), findsNothing);
      expect(find.text('alliance'), findsNothing);
      expect(find.text('assembly drawings'), findsNothing);
    });
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

  testWidgets(
    'reauthentication-required provider shows banner but keeps other results',
    (tester) async {
      final api = FakeSearchApi(
        (_) async => _response(
          providers: [
            const ProviderOutcome(
              providerId: 'mock',
              status: 'success',
              resultCount: 1,
            ),
            const ProviderOutcome(
              providerId: 'alliance',
              status: 'reauthentication_required',
            ),
          ],
        ),
      );
      await _pumpAppAndSearch(tester, _app(api));
      await tester.pumpAndSettle();

      // Degraded state surfaced…
      expect(find.byKey(const Key('partial-failure-banner')), findsOneWidget);
      expect(find.textContaining('alliance'), findsOneWidget);
      // …without hiding the successful provider's results.
      expect(find.text('SC60 Service Manual (sample)'), findsOneWidget);
    },
  );

  testWidgets('blank query does not trigger a search', (tester) async {
    final api = FakeSearchApi((_) async => _response());
    await tester.pumpWidget(_app(api));
    await tester.tap(find.byKey(const Key('search-button')));
    await tester.pumpAndSettle();

    expect(api.queries, isEmpty);
    expect(find.textContaining('Search manuals, parts'), findsOneWidget);
  });
}
