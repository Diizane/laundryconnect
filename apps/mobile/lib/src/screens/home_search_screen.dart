import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../models/machine.dart';
import '../models/search.dart';
import '../storage/workspace_store.dart';
import '../theme/app_theme.dart';
import '../widgets/result_card.dart';
import 'machine_workspace_screen.dart';

/// Home screen: universal search bar first, results below on the same
/// screen — a technician standing at a machine gets from launch to answer
/// with one tap and one query.
class HomeSearchScreen extends StatefulWidget {
  const HomeSearchScreen({
    super.key,
    required this.searchApi,
    required this.machinesApi,
    required this.store,
  });

  final SearchApi searchApi;
  final MachinesApi machinesApi;
  final WorkspaceStore store;

  @override
  State<HomeSearchScreen> createState() => _HomeSearchScreenState();
}

sealed class _SearchState {
  const _SearchState();
}

class _Idle extends _SearchState {
  const _Idle();
}

class _Loading extends _SearchState {
  const _Loading();
}

class _Failed extends _SearchState {
  const _Failed(this.message);

  final String message;
}

class _Loaded extends _SearchState {
  const _Loaded(this.response);

  final SearchResponse response;
}

class _HomeSearchScreenState extends State<HomeSearchScreen> {
  final _controller = TextEditingController();
  _SearchState _state = const _Idle();
  int _requestSequence = 0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _search() async {
    final query = _controller.text.trim();
    if (query.isEmpty) return;

    final sequence = ++_requestSequence;
    setState(() => _state = const _Loading());
    try {
      final response = await widget.searchApi.search(query);
      if (!mounted || sequence != _requestSequence) return;
      setState(() => _state = _Loaded(response));
    } on ApiException catch (error) {
      if (!mounted || sequence != _requestSequence) return;
      setState(() => _state = _Failed(error.message));
    }
  }

  /// Open the machine workspace for a search result's model, if the
  /// catalog knows it.
  Future<void> _openWorkspaceForResult(SearchResult result) async {
    final model = result.model;
    if (model == null) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      final machines = await widget.machinesApi.findByModelNumber(model);
      if (!mounted) return;
      if (machines.isEmpty) {
        messenger.showSnackBar(
          SnackBar(content: Text('No workspace available for $model yet.')),
        );
        return;
      }
      await _openWorkspace(machines.first);
    } on ApiException catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.message)));
    }
  }

  Future<void> _openWorkspace(MachineSummary machine) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => MachineWorkspaceScreen(
          machine: machine,
          machinesApi: widget.machinesApi,
          store: widget.store,
        ),
      ),
    );
    // Refresh recents/bookmarks shown in the idle state.
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('LaundryConnect')),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: TextField(
                controller: _controller,
                textInputAction: TextInputAction.search,
                onSubmitted: (_) => _search(),
                decoration: InputDecoration(
                  hintText: 'Model, serial, part number, fault code…',
                  prefixIcon: const Icon(Icons.search),
                  suffixIcon: IconButton(
                    key: const Key('search-button'),
                    icon: const Icon(Icons.arrow_forward),
                    onPressed: _search,
                    tooltip: 'Search',
                  ),
                ),
              ),
            ),
            Expanded(child: _buildBody()),
          ],
        ),
      ),
    );
  }

  Widget _buildBody() {
    return switch (_state) {
      _Idle() => _IdleView(store: widget.store, onOpenMachine: _openWorkspace),
      _Loading() => const Center(child: CircularProgressIndicator()),
      _Failed(:final message) => _ErrorView(message: message, onRetry: _search),
      _Loaded(:final response) => _ResultsView(
        response: response,
        onResultTap: _openWorkspaceForResult,
      ),
    };
  }
}

/// Idle state: hint plus locally stored bookmarks and recent machines so a
/// returning technician can skip the search entirely.
class _IdleView extends StatelessWidget {
  const _IdleView({required this.store, required this.onOpenMachine});

  final WorkspaceStore store;
  final void Function(MachineSummary) onOpenMachine;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<List<MachineSummary>>>(
      future: Future.wait([store.bookmarkedMachines(), store.recentMachines()]),
      builder: (context, snapshot) {
        final bookmarks = snapshot.data?[0] ?? const <MachineSummary>[];
        final recents = snapshot.data?[1] ?? const <MachineSummary>[];
        if (bookmarks.isEmpty && recents.isEmpty) {
          return const _EmptyHint();
        }
        return ListView(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          children: [
            if (bookmarks.isNotEmpty) ...[
              _SectionLabel('Bookmarked machines'),
              _MachineChips(machines: bookmarks, onTap: onOpenMachine),
            ],
            if (recents.isNotEmpty) ...[
              _SectionLabel('Recent machines'),
              _MachineChips(machines: recents, onTap: onOpenMachine),
            ],
          ],
        );
      },
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 8, bottom: 8),
      child: Text(
        label,
        style: Theme.of(context).textTheme.titleMedium?.copyWith(
          fontWeight: FontWeight.w700,
          color: AppColors.navy,
        ),
      ),
    );
  }
}

class _MachineChips extends StatelessWidget {
  const _MachineChips({required this.machines, required this.onTap});

  final List<MachineSummary> machines;
  final void Function(MachineSummary) onTap;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final machine in machines)
          ActionChip(
            avatar: const Icon(Icons.local_laundry_service_outlined, size: 18),
            label: Text('${machine.modelNumber} · ${machine.brand}'),
            onPressed: () => onTap(machine),
          ),
      ],
    );
  }
}

class _EmptyHint extends StatelessWidget {
  const _EmptyHint();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.local_laundry_service_outlined,
              size: 56,
              color: theme.colorScheme.primary.withValues(alpha: 0.4),
            ),
            const SizedBox(height: 16),
            Text(
              'Search manuals, parts, wiring and fault codes\nacross all your providers.',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium,
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.cloud_off_outlined,
              size: 48,
              color: AppColors.danger,
            ),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}

class _ResultsView extends StatelessWidget {
  const _ResultsView({required this.response, required this.onResultTap});

  final SearchResponse response;
  final void Function(SearchResult) onResultTap;

  @override
  Widget build(BuildContext context) {
    if (response.totalResults == 0) {
      return Center(
        child: Text(
          'No results for "${response.query}".\nTry a different model, part, or keyword.',
          textAlign: TextAlign.center,
        ),
      );
    }

    final degraded = response.degradedProviders;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      children: [
        if (degraded.isNotEmpty) _PartialFailureBanner(providers: degraded),
        for (final group in response.groups) ...[
          _GroupHeader(group: group),
          for (final result in group.results)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: ResultCard(
                result: result,
                onTap: () => onResultTap(result),
              ),
            ),
        ],
      ],
    );
  }
}

class _GroupHeader extends StatelessWidget {
  const _GroupHeader({required this.group});

  final MachineGroup group;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final title = group.model ?? 'Other results';
    final subtitle = [
      group.brand,
      group.manufacturer,
    ].whereType<String>().toSet().join(' · ');
    return Padding(
      padding: const EdgeInsets.only(top: 8, bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(
            title,
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w700,
              color: AppColors.navy,
            ),
          ),
          if (subtitle.isNotEmpty) ...[
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                subtitle,
                style: theme.textTheme.bodySmall,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Shown when some providers failed or timed out: results are partial, and
/// the technician should know rather than silently trust an incomplete list.
class _PartialFailureBanner extends StatelessWidget {
  const _PartialFailureBanner({required this.providers});

  final List<ProviderOutcome> providers;

  @override
  Widget build(BuildContext context) {
    final names = providers.map((p) => p.providerId).join(', ');
    return Container(
      key: const Key('partial-failure-banner'),
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.warning.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          const Icon(
            Icons.warning_amber_outlined,
            color: AppColors.warning,
            size: 20,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Some sources unavailable: $names. Results may be incomplete.',
              style: const TextStyle(fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }
}
