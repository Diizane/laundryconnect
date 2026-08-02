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
    ProviderDocumentsApi? providerDocumentsApi,
    WorkspaceStore? store,
  }) : searchApi = searchApi ?? HttpSearchApi(),
       machinesApi = machinesApi ?? HttpMachinesApi(),
       documentsApi = documentsApi ?? HttpDocumentsApi(),
       providerDocumentsApi =
           providerDocumentsApi ?? HttpProviderDocumentsApi(),
       store = store ?? SharedPrefsWorkspaceStore();

  /// Injectable for widget tests; defaults to the real backend clients.
  final SearchApi searchApi;
  final MachinesApi machinesApi;
  final DocumentsApi documentsApi;
  final ProviderDocumentsApi providerDocumentsApi;
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
        providerDocumentsApi: providerDocumentsApi,
        store: store,
      ),
    );
  }
}
