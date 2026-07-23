import 'package:flutter_test/flutter_test.dart';
import 'package:laundryconnect/src/models/machine.dart';
import 'package:laundryconnect/src/storage/workspace_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'fakes.dart';

MachineSummary _machine(String id) => MachineSummary(
  id: id,
  modelNumber: 'M-$id',
  brand: 'Brand',
  manufacturer: 'Maker',
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('recents are most-recent-first and deduplicated', () async {
    final store = SharedPrefsWorkspaceStore();
    await store.addRecent(_machine('a'));
    await store.addRecent(_machine('b'));
    await store.addRecent(_machine('a')); // re-open moves to front

    final recents = await store.recentMachines();
    expect(recents.map((m) => m.id), ['a', 'b']);
  });

  test('recents are capped at ten', () async {
    final store = SharedPrefsWorkspaceStore();
    for (var i = 0; i < 12; i++) {
      await store.addRecent(_machine('m$i'));
    }
    final recents = await store.recentMachines();
    expect(recents, hasLength(10));
    expect(recents.first.id, 'm11');
  });

  test('bookmark toggle adds and removes', () async {
    final store = SharedPrefsWorkspaceStore();
    expect(await store.toggleBookmark(sc60), isTrue);
    expect(await store.isBookmarked(sc60.id), isTrue);
    expect((await store.bookmarkedMachines()).map((m) => m.id), [sc60.id]);

    expect(await store.toggleBookmark(sc60), isFalse);
    expect(await store.isBookmarked(sc60.id), isFalse);
    expect(await store.bookmarkedMachines(), isEmpty);
  });

  test('round-trips machine metadata through JSON', () async {
    final store = SharedPrefsWorkspaceStore();
    await store.addRecent(sc60);
    final [restored] = await store.recentMachines();
    expect(restored.modelNumber, 'SC60');
    expect(restored.brand, 'Speed Queen');
    expect(restored.manufacturer, 'Alliance Laundry Systems');
    expect(restored.machineType, 'washer_extractor');
    expect(restored.family, 'SC series');
  });
}
