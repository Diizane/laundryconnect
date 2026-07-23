import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:laundryconnect/src/api/api_client.dart';
import 'package:laundryconnect/src/models/machine.dart';
import 'package:laundryconnect/src/screens/machine_workspace_screen.dart';
import 'package:laundryconnect/src/theme/app_theme.dart';

import 'fakes.dart';

Future<void> _pumpWorkspace(
  WidgetTester tester, {
  required FakeMachinesApi api,
  required FakeWorkspaceStore store,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: buildAppTheme(),
      home: MachineWorkspaceScreen(
        machine: sc60,
        machinesApi: api,
        documentsApi: FakeDocumentsApi(),
        store: store,
      ),
    ),
  );
}

void main() {
  testWidgets('shows machine metadata and grouped documents', (tester) async {
    final store = FakeWorkspaceStore();
    await _pumpWorkspace(tester, api: FakeMachinesApi(), store: store);
    await tester.pumpAndSettle();

    expect(find.text('SC60'), findsOneWidget); // app bar
    expect(find.textContaining('Speed Queen'), findsOneWidget); // header
    expect(find.text('Manuals'), findsOneWidget); // category label
    expect(find.text('Wiring'), findsOneWidget);
    expect(find.text('SC60 Service Manual (sample)'), findsOneWidget);
    expect(find.text('Rev 4'), findsOneWidget);
  });

  testWidgets('records the machine as recently viewed', (tester) async {
    final store = FakeWorkspaceStore();
    await _pumpWorkspace(tester, api: FakeMachinesApi(), store: store);
    await tester.pumpAndSettle();

    expect(store.recents.map((m) => m.id), ['machine-1']);
  });

  testWidgets('shows loading indicator while fetching documents', (
    tester,
  ) async {
    final completer = Completer<MachineDocuments>();
    final api = FakeMachinesApi(documentsHandler: (_) => completer.future);
    await _pumpWorkspace(tester, api: api, store: FakeWorkspaceStore());
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    completer.complete(sc60Documents());
    await tester.pumpAndSettle();
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('shows error with retry when documents fail to load', (
    tester,
  ) async {
    var calls = 0;
    final api = FakeMachinesApi(
      documentsHandler: (_) {
        calls++;
        if (calls == 1) {
          return Future.error(const ApiException('Cannot reach the server.'));
        }
        return Future.value(sc60Documents());
      },
    );
    await _pumpWorkspace(tester, api: api, store: FakeWorkspaceStore());
    await tester.pumpAndSettle();

    expect(find.text('Cannot reach the server.'), findsOneWidget);

    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    expect(find.text('SC60 Service Manual (sample)'), findsOneWidget);
  });

  testWidgets('bookmark toggle persists through the store', (tester) async {
    final store = FakeWorkspaceStore();
    await _pumpWorkspace(tester, api: FakeMachinesApi(), store: store);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('bookmark-button')));
    await tester.pumpAndSettle();
    expect(store.bookmarks.map((m) => m.id), ['machine-1']);
    expect(find.byIcon(Icons.bookmark), findsOneWidget);

    await tester.tap(find.byKey(const Key('bookmark-button')));
    await tester.pumpAndSettle();
    expect(store.bookmarks, isEmpty);
    expect(find.byIcon(Icons.bookmark_outline), findsOneWidget);
  });
}
