import 'package:laundryconnect/src/api/api_client.dart';
import 'package:laundryconnect/src/models/machine.dart';
import 'package:laundryconnect/src/models/search.dart';
import 'package:laundryconnect/src/storage/workspace_store.dart';

const sc60 = MachineSummary(
  id: 'machine-1',
  modelNumber: 'SC60',
  brand: 'Speed Queen',
  manufacturer: 'Alliance Laundry Systems',
  machineType: 'washer_extractor',
  family: 'SC series',
);

MachineDocuments sc60Documents() => const MachineDocuments(
  machine: sc60,
  categories: [
    DocumentCategory(
      documentType: 'service_manual',
      documents: [
        DocumentItem(
          id: 'doc-1',
          title: 'SC60 Service Manual (sample)',
          documentType: 'service_manual',
          provider: 'mock',
          revision: 'Rev 4',
        ),
      ],
    ),
    DocumentCategory(
      documentType: 'wiring_diagram',
      documents: [
        DocumentItem(
          id: 'doc-2',
          title: 'SC60 Wiring Diagram (sample)',
          documentType: 'wiring_diagram',
          provider: 'mock',
        ),
      ],
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

class FakeMachinesApi implements MachinesApi {
  FakeMachinesApi({this.machines = const [sc60], this.documentsHandler});

  final List<MachineSummary> machines;
  final Future<MachineDocuments> Function(String machineId)? documentsHandler;

  @override
  Future<List<MachineSummary>> findByModelNumber(String modelNumber) async =>
      machines
          .where(
            (m) => m.modelNumber.toLowerCase() == modelNumber.toLowerCase(),
          )
          .toList();

  @override
  Future<MachineDocuments> machineDocuments(String machineId) {
    final handler = documentsHandler;
    if (handler != null) return handler(machineId);
    return Future.value(sc60Documents());
  }
}

/// In-memory store so widget tests need no shared_preferences plugin.
class FakeWorkspaceStore implements WorkspaceStore {
  final recents = <MachineSummary>[];
  final bookmarks = <MachineSummary>[];

  @override
  Future<void> addRecent(MachineSummary machine) async {
    recents.removeWhere((m) => m.id == machine.id);
    recents.insert(0, machine);
  }

  @override
  Future<List<MachineSummary>> recentMachines() async => List.of(recents);

  @override
  Future<List<MachineSummary>> bookmarkedMachines() async => List.of(bookmarks);

  @override
  Future<bool> isBookmarked(String machineId) async =>
      bookmarks.any((m) => m.id == machineId);

  @override
  Future<bool> toggleBookmark(MachineSummary machine) async {
    final was = bookmarks.any((m) => m.id == machine.id);
    if (was) {
      bookmarks.removeWhere((m) => m.id == machine.id);
    } else {
      bookmarks.insert(0, machine);
    }
    return !was;
  }
}
