import 'dart:typed_data';

import 'package:laundryconnect/src/api/api_client.dart';
import 'package:laundryconnect/src/models/document_search.dart';
import 'package:laundryconnect/src/models/machine.dart';
import 'package:laundryconnect/src/models/provider_documents.dart';
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
          origin: 'seeded_sample',
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
          origin: 'seeded_sample',
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

const sampleServiceManual = DocumentItem(
  id: 'doc-1',
  title: 'SC60 Service Manual (sample)',
  documentType: 'service_manual',
  provider: 'mock',
  origin: 'seeded_sample',
  revision: 'Rev 4',
);

class FakeDocumentsApi implements DocumentsApi {
  FakeDocumentsApi({this.searchHandler, this.pageHandler});

  final Future<DocumentSearchResult> Function(String documentId, String query)?
  searchHandler;
  final Future<DocumentPageContent> Function(String documentId, int pageNumber)?
  pageHandler;

  @override
  Future<DocumentSearchResult> searchInDocument(
    String documentId,
    String query,
  ) {
    final handler = searchHandler;
    if (handler != null) return handler(documentId, query);
    return Future.value(
      DocumentSearchResult(
        query: query,
        totalHits: 1,
        hits: [
          PageSearchHit(
            documentId: documentId,
            documentTitle: 'SC60 Service Manual (sample)',
            provider: 'mock',
            pageNumber: 2,
            snippet: '…EdL: door lock error - check assembly F8524501…',
          ),
        ],
      ),
    );
  }

  @override
  Future<DocumentPageContent> getPage(String documentId, int pageNumber) {
    final handler = pageHandler;
    if (handler != null) return handler(documentId, pageNumber);
    return Future.value(
      DocumentPageContent(
        pageNumber: pageNumber,
        textContent:
            'SAMPLE PAGE $pageNumber. Fault code table. EdL: door lock error.',
        textSource: 'seeded_sample',
      ),
    );
  }
}

DocumentContents sampleContents({
  bool searchable = true,
  List<ContentsEntry>? contents,
}) => DocumentContents(
  pageCount: 82,
  searchable: searchable,
  searchablePages: searchable ? 81 : 0,
  contents:
      contents ??
      const [
        ContentsEntry(title: 'Cover', pageNumber: 1),
        ContentsEntry(title: 'Drum Drive', pageNumber: 47, depth: 1),
      ],
);

DrawingDetail sampleDrawing({String? svg}) => DrawingDetail(
  svg:
      svg ??
      '<svg xmlns="http://www.w3.org/2000/svg" width="7.74in" height="9.71in" '
          'viewBox="0 0 100 100"><circle cx="50" cy="50" r="40"/></svg>',
  parts: const [
    DrawingPart(
      reference: '7',
      partNumber: 'M412025P',
      description: 'Burner',
      comments: '3 required',
    ),
    DrawingPart(reference: '8', partNumber: 'SP533157', description: 'Belt'),
  ],
);

final samplePdfBytes = Uint8List.fromList('%PDF-1.4 fake'.codeUnits);

DownloadedDocument sampleDownload({
  String origin = 'live',
  int ageSeconds = 0,
}) => DownloadedDocument(
  bytes: samplePdfBytes,
  origin: origin,
  ageSeconds: ageSeconds,
);

DocumentDiscovery sampleDiscovery({String tokenSuffix = ''}) =>
    DocumentDiscovery(
      providerId: 'alliance',
      documents: [
        ProviderDocument(
          token: 'token-technical$tokenSuffix',
          title: 'D0568 — Technical Mnl',
          documentType: 'Technical Mnl',
          partNumber: 'D0568',
          comment: 'Date 9/99',
          languages: const ['English'],
          category: 'Production',
          filename: 'D0568.pdf',
          available: true,
          dataOrigin: 'fixture',
        ),
        const ProviderDocument(
          token: null,
          title: 'D0300 — Legacy Bulletin',
          documentType: 'Bulletin',
          partNumber: 'D0300',
          comment: 'Printed only',
          languages: ['English'],
          category: null,
          filename: null,
          available: false,
          dataOrigin: 'fixture',
        ),
      ],
    );

class FakeProviderDocumentsApi implements ProviderDocumentsApi {
  FakeProviderDocumentsApi({
    this.discoverHandler,
    this.downloadHandler,
    this.contentsHandler,
    this.searchHandler,
    this.drawingsHandler,
    this.drawingHandler,
  });

  Future<DocumentDiscovery> Function(String providerId, String ref)?
  discoverHandler;
  Future<DownloadedDocument> Function(String providerId, String token)?
  downloadHandler;
  Future<DocumentContents> Function(String providerId, String token)?
  contentsHandler;
  Future<DocumentSearchResults> Function(
    String providerId,
    String token,
    String query,
  )?
  searchHandler;
  Future<List<DrawingSummary>> Function(String providerId, String ref)?
  drawingsHandler;
  Future<DrawingDetail> Function(String providerId, String token)?
  drawingHandler;

  final discoverCalls = <String>[];
  final downloadCalls = <String>[];
  final contentsCalls = <String>[];
  final searchCalls = <String>[];
  final drawingListCalls = <String>[];
  final drawingCalls = <String>[];

  @override
  Future<DocumentDiscovery> discoverDocuments(String providerId, String ref) {
    discoverCalls.add(ref);
    final handler = discoverHandler;
    if (handler != null) return handler(providerId, ref);
    return Future.value(sampleDiscovery());
  }

  @override
  Future<DownloadedDocument> downloadDocument(String providerId, String token) {
    downloadCalls.add(token);
    final handler = downloadHandler;
    if (handler != null) return handler(providerId, token);
    return Future.value(sampleDownload());
  }

  @override
  Future<List<DrawingSummary>> discoverDrawings(String providerId, String ref) {
    drawingListCalls.add(ref);
    final handler = drawingsHandler;
    if (handler != null) return handler(providerId, ref);
    return Future.value(const [
      DrawingSummary(token: 'token-drive', title: 'Drive', drawingId: '548226'),
      DrawingSummary(token: 'token-frame', title: 'Frame', drawingId: '548172'),
    ]);
  }

  @override
  Future<DrawingDetail> fetchDrawing(String providerId, String token) {
    drawingCalls.add(token);
    final handler = drawingHandler;
    if (handler != null) return handler(providerId, token);
    return Future.value(sampleDrawing());
  }

  @override
  Future<DocumentContents> documentContents(String providerId, String token) {
    contentsCalls.add(token);
    final handler = contentsHandler;
    if (handler != null) return handler(providerId, token);
    return Future.value(sampleContents());
  }

  @override
  Future<DocumentSearchResults> searchWithinDocument(
    String providerId,
    String token,
    String query,
  ) {
    searchCalls.add(query);
    final handler = searchHandler;
    if (handler != null) return handler(providerId, token, query);
    return Future.value(
      DocumentSearchResults(
        query: query,
        searchable: true,
        hits: const [
          DocumentSearchHit(
            pageNumber: 47,
            snippet: '…SMIT Drum Drive - DR20 Models REF PART NO…',
          ),
        ],
      ),
    );
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
