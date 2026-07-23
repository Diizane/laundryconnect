import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/machine.dart';

/// Local (on-device) recents and bookmarks.
///
/// Foundation only: stored per device via shared_preferences. When technician
/// accounts arrive, this becomes a cache in front of server-side sync.
abstract interface class WorkspaceStore {
  Future<List<MachineSummary>> recentMachines();

  Future<void> addRecent(MachineSummary machine);

  Future<List<MachineSummary>> bookmarkedMachines();

  Future<bool> isBookmarked(String machineId);

  /// Toggles and returns the new bookmarked state.
  Future<bool> toggleBookmark(MachineSummary machine);
}

class SharedPrefsWorkspaceStore implements WorkspaceStore {
  static const _recentsKey = 'recent_machines';
  static const _bookmarksKey = 'bookmarked_machines';
  static const _maxRecents = 10;

  Future<List<MachineSummary>> _read(String key) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(key);
    if (raw == null) return [];
    try {
      return (jsonDecode(raw) as List<dynamic>)
          .map((m) => MachineSummary.fromJson(m as Map<String, dynamic>))
          .toList();
    } on FormatException {
      return [];
    } on TypeError {
      return [];
    }
  }

  Future<void> _write(String key, List<MachineSummary> machines) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      key,
      jsonEncode(machines.map((m) => m.toJson()).toList()),
    );
  }

  @override
  Future<List<MachineSummary>> recentMachines() => _read(_recentsKey);

  @override
  Future<void> addRecent(MachineSummary machine) async {
    final recents = await _read(_recentsKey);
    recents.removeWhere((m) => m.id == machine.id);
    recents.insert(0, machine);
    await _write(_recentsKey, recents.take(_maxRecents).toList());
  }

  @override
  Future<List<MachineSummary>> bookmarkedMachines() => _read(_bookmarksKey);

  @override
  Future<bool> isBookmarked(String machineId) async {
    final bookmarks = await _read(_bookmarksKey);
    return bookmarks.any((m) => m.id == machineId);
  }

  @override
  Future<bool> toggleBookmark(MachineSummary machine) async {
    final bookmarks = await _read(_bookmarksKey);
    final wasBookmarked = bookmarks.any((m) => m.id == machine.id);
    if (wasBookmarked) {
      bookmarks.removeWhere((m) => m.id == machine.id);
    } else {
      bookmarks.insert(0, machine);
    }
    await _write(_bookmarksKey, bookmarks);
    return !wasBookmarked;
  }
}
