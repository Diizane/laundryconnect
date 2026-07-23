import 'package:flutter/material.dart';

import 'api/api_client.dart';
import 'screens/home_search_screen.dart';
import 'theme/app_theme.dart';

class LaundryConnectApp extends StatelessWidget {
  LaundryConnectApp({super.key, SearchApi? searchApi})
    : searchApi = searchApi ?? HttpSearchApi();

  /// Injectable for widget tests; defaults to the real backend client.
  final SearchApi searchApi;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'LaundryConnect',
      theme: buildAppTheme(),
      debugShowCheckedModeBanner: false,
      home: HomeSearchScreen(searchApi: searchApi),
    );
  }
}
