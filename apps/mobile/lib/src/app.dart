import 'package:flutter/material.dart';

import 'api/api_client.dart';
import 'screens/home_search_screen.dart';
import 'storage/workspace_store.dart';
import 'theme/app_theme.dart';

class LaundryConnectApp extends StatelessWidget {
  LaundryConnectApp({
    super.key,
    SearchApi? searchApi,
    MachinesApi? machinesApi,
    DocumentsApi? documentsApi,
    WorkspaceStore? store,
  }) : searchApi = searchApi ?? HttpSearchApi(),
       machinesApi = machinesApi ?? HttpMachinesApi(),
       documentsApi = documentsApi ?? HttpDocumentsApi(),
       store = store ?? SharedPrefsWorkspaceStore();

  /// Injectable for widget tests; defaults to the real backend clients.
  final SearchApi searchApi;
  final MachinesApi machinesApi;
  final DocumentsApi documentsApi;
  final WorkspaceStore store;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'LaundryConnect',
      theme: buildAppTheme(),
      debugShowCheckedModeBanner: false,
      home: HomeSearchScreen(
        searchApi: searchApi,
        machinesApi: machinesApi,
        documentsApi: documentsApi,
        store: store,
      ),
    );
  }
}
