import 'dart:async';

import 'package:flutter/material.dart';

import 'src/local_store.dart';
import 'src/models.dart';
import 'src/view_model.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MerchantCopilotApp());
}

class MerchantCopilotApp extends StatefulWidget {
  const MerchantCopilotApp({super.key, this.viewModel});
  final MerchantViewModel? viewModel;
  @override
  State<MerchantCopilotApp> createState() => _MerchantCopilotAppState();
}

class _MerchantCopilotAppState extends State<MerchantCopilotApp>
    with WidgetsBindingObserver {
  MerchantViewModel? model;
  String? bootError;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    model = widget.viewModel;
    if (model == null) unawaited(_boot());
  }

  Future<void> _boot() async {
    try {
      final store = await LocalStore.open();
      if (!mounted) {
        await store.close();
        return;
      }
      final vm = MerchantViewModel(store: store);
      setState(() {
        model = vm;
        bootError = null;
      });
      await vm.initialize();
    } catch (_) {
      if (mounted) setState(() => bootError = '本地数据库无法打开，请重试。原有记录不会自动删除。');
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(model?.resume());
    } else if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached) {
      model?.suspend();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    if (widget.viewModel == null) model?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    title: 'MerchantCopilot',
    theme: ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff185b52)),
      scaffoldBackgroundColor: const Color(0xfff6f7f4),
      cardTheme: const CardThemeData(
        elevation: 0,
        margin: EdgeInsets.symmetric(vertical: 6),
      ),
      inputDecorationTheme: const InputDecorationTheme(
        border: OutlineInputBorder(),
      ),
    ),
    home: model == null
        ? Scaffold(
            body: Center(
              child: bootError == null
                  ? const CircularProgressIndicator()
                  : Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(bootError!),
                        TextButton(onPressed: _boot, child: const Text('重试')),
                      ],
                    ),
            ),
          )
        : _Home(model!),
  );
}

class _Home extends StatefulWidget {
  const _Home(this.vm);
  final MerchantViewModel vm;
  @override
  State<_Home> createState() => _HomeState();
}

class _HomeState extends State<_Home> {
  int tab = 0;
  void detail() => Navigator.of(
    context,
  ).push(MaterialPageRoute<void>(builder: (_) => _AnalysisPage(widget.vm)));
  void settings() => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => AnimatedBuilder(
        animation: widget.vm,
        builder: (context, _) => Scaffold(
          appBar: AppBar(title: const Text('设置')),
          body: SafeArea(
            child: Column(
              children: [
                if (widget.vm.state.problem != null)
                  _Problem(
                    widget.vm.state.problem!,
                    onRetry: widget.vm.refresh,
                  ),
                Expanded(
                  child: _SettingsPage(
                    widget.vm,
                    key: ValueKey(widget.vm.settingsRevision),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );
  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: widget.vm,
    builder: (context, _) {
      final state = widget.vm.state;
      return Scaffold(
        appBar: AppBar(
          title: const Text('MerchantCopilot'),
          actions: [
            IconButton(
              key: const Key('open_settings'),
              tooltip: '设置',
              onPressed: settings,
              icon: const Icon(Icons.settings_outlined),
            ),
            IconButton(
              tooltip: '刷新',
              onPressed: state.busy ? null : widget.vm.refresh,
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        body: SafeArea(
          child: Column(
            children: [
              const _SyntheticLabel(),
              if (state.phase == ScreenPhase.loading ||
                  state.phase == ScreenPhase.recovering)
                const LinearProgressIndicator(minHeight: 2),
              if (state.problem != null)
                _Problem(state.problem!, onRetry: widget.vm.refresh),
              Expanded(
                child: IndexedStack(
                  index: tab,
                  children: [
                    _OverviewPage(
                      widget.vm,
                      openAnalysis: detail,
                      configure: settings,
                    ),
                    _HistoryPage(widget.vm, openAnalysis: detail),
                    _MemoryPage(widget.vm),
                  ],
                ),
              ),
            ],
          ),
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: tab,
          onDestinationSelected: (value) => setState(() => tab = value),
          destinations: const [
            NavigationDestination(
              icon: Icon(Icons.space_dashboard_outlined),
              label: '概览',
            ),
            NavigationDestination(icon: Icon(Icons.history), label: '记录'),
            NavigationDestination(
              icon: Icon(Icons.storefront_outlined),
              label: '经营信息',
            ),
          ],
        ),
      );
    },
  );
}

class _SyntheticLabel extends StatelessWidget {
  const _SyntheticLabel();
  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    color: const Color(0xffe8f0e8),
    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
    child: const Text(
      '小张女装 · 受控合成数据演示',
      style: TextStyle(fontSize: 12, color: Color(0xff355648)),
    ),
  );
}

class _OverviewPage extends StatelessWidget {
  const _OverviewPage(
    this.vm, {
    required this.openAnalysis,
    required this.configure,
  });
  final MerchantViewModel vm;
  final VoidCallback openAnalysis;
  final VoidCallback configure;

  Future<void> _range(BuildContext context) async {
    final data = vm.state.overview;
    if (data == null) return;
    final first = DateTime.tryParse(data['available_from']?.toString() ?? '');
    final last = DateTime.tryParse(data['available_to']?.toString() ?? '');
    if (first == null || last == null) return;
    final range = await showDateRangePicker(
      context: context,
      firstDate: first,
      lastDate: last,
      initialDateRange: DateTimeRange(
        start: DateTime.parse(vm.state.startDate),
        end: DateTime.parse(vm.state.endDate),
      ),
      helpText: '选择合成数据日期',
    );
    if (range != null)
      await vm.refreshOverview(
        start: _date(range.start),
        end: _date(range.end),
      );
  }

  @override
  Widget build(BuildContext context) {
    final state = vm.state;
    final overview = state.overview;
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text('看清变化，再做决定', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 8),
        const Text('从经营指标进入分析，查看依据，再决定下一步。'),
        const SizedBox(height: 18),
        if (!vm.settings.isConfigured)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('连接你的本地演示服务'),
                  const SizedBox(height: 8),
                  FilledButton(
                    onPressed: configure,
                    child: const Text('设置服务地址与 token'),
                  ),
                ],
              ),
            ),
          ),
        if (overview != null) ...[
          OutlinedButton.icon(
            onPressed: state.busy ? null : () => _range(context),
            icon: const Icon(Icons.calendar_today_outlined, size: 18),
            label: Text('${state.startDate} — ${state.endDate}'),
          ),
          Text(
            '数据截至 ${overview['data_as_of'] ?? state.endDate}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (state.connection != LiveConnection.online)
            Text(
              '本地快照 · ${overview['_cached_at'] ?? ''}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          const SizedBox(height: 8),
          for (final metric in overview['metrics'] as List? ?? [])
            Card(
              child: ListTile(
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 18,
                  vertical: 12,
                ),
                title: Text(
                  (metric as Map)['label']?.toString() ??
                      metric['key'].toString(),
                ),
                subtitle: Text(
                  '${metric['value'] ?? '—'} ${metric['unit'] ?? ''}',
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                trailing: const Icon(Icons.arrow_forward),
                onTap: () async {
                  await vm.prepareAnalysis(
                    metric['key'].toString().toLowerCase() == 'gmv'
                        ? '检查 ${state.startDate} 至 ${state.endDate} 的GMV是否下跌；若下跌，分析原因并列出证据；未下跌则说明数据。'
                        : '分析 ${state.startDate} 至 ${state.endDate} 的${metric['label'] ?? metric['key']}，给出证据与下一步建议。',
                    context: {
                      'metric': metric['key'],
                      'start_date': state.startDate,
                      'end_date': state.endDate,
                    },
                  );
                  openAnalysis();
                },
              ),
            ),
          _EvidenceList(
            (overview['evidence'] as List? ?? [])
                .map(EvidenceItem.fromJson)
                .toList(),
          ),
        ] else if (vm.settings.isConfigured)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 36),
            child: Text('尚无指标快照。连接服务后点击右上角刷新。'),
          ),
        const SizedBox(height: 16),
        OutlinedButton.icon(
          onPressed: openAnalysis,
          icon: const Icon(Icons.chat_bubble_outline),
          label: const Text('提出经营问题'),
        ),
        if (state.hasPending || state.run != null && !state.run!.terminal)
          TextButton(onPressed: openAnalysis, child: const Text('继续查看未完成任务')),
      ],
    );
  }
}

class _HistoryPage extends StatelessWidget {
  const _HistoryPage(this.vm, {required this.openAnalysis});
  final MerchantViewModel vm;
  final VoidCallback openAnalysis;
  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(20),
    children: [
      Text('分析任务', style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 8),
      const Text('退出后可从这里恢复。连接中断时保留最近一次状态。'),
      if (vm.state.hasPending)
        Card(
          child: ListTile(
            leading: const Icon(Icons.sync_problem),
            title: const Text('有一项请求等待确认'),
            subtitle: const Text('恢复会使用原请求，不会重新创建分析。'),
            trailing: TextButton(
              onPressed: vm.state.busy ? null : vm.refresh,
              child: const Text('恢复'),
            ),
          ),
        ),
      if (vm.state.history.isEmpty)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 36),
          child: Text('尚无分析任务。先从概览选择指标。'),
        ),
      for (final run in vm.state.history)
        Card(
          child: ListTile(
            title: Text(
              run.query,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            subtitle: Text(
              '${_status(run.status)} · ${run.createdAt}\n${run.id}',
            ),
            isThreeLine: true,
            trailing: const Icon(Icons.chevron_right),
            onTap: () {
              unawaited(vm.openRun(run.id));
              openAnalysis();
            },
          ),
        ),
      if (vm.state.moreHistory)
        TextButton(
          onPressed: () => vm.refreshHistory(more: true),
          child: const Text('加载更多'),
        ),
    ],
  );
}

class _AnalysisPage extends StatefulWidget {
  const _AnalysisPage(this.vm);
  final MerchantViewModel vm;
  @override
  State<_AnalysisPage> createState() => _AnalysisPageState();
}

class _AnalysisPageState extends State<_AnalysisPage> {
  late final input = TextEditingController(text: widget.vm.state.draft);
  Timer? debounce;
  @override
  void dispose() {
    debounce?.cancel();
    input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: widget.vm,
    builder: (context, _) {
      final state = widget.vm.state;
      final run = state.run;
      return Scaffold(
        appBar: AppBar(title: const Text('经营分析')),
        body: SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              const _SyntheticLabel(),
              const SizedBox(height: 16),
              TextField(
                key: const Key('query_input'),
                controller: input,
                minLines: 2,
                maxLines: 5,
                enabled: state.canSubmit,
                decoration: const InputDecoration(labelText: '经营问题'),
                onChanged: (value) {
                  debounce?.cancel();
                  debounce = Timer(
                    const Duration(milliseconds: 250),
                    () => widget.vm.setDraft(value),
                  );
                },
              ),
              if (state.context != null) ...[
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    '分析范围：${state.context!['metric']} · ${state.context!['start_date']} — ${state.context!['end_date']}',
                  ),
                ),
                TextButton(
                  onPressed: state.canSubmit
                      ? () => widget.vm.setDraft(input.text, clearContext: true)
                      : null,
                  child: const Text('清除指标范围'),
                ),
              ],
              const SizedBox(height: 12),
              FilledButton.icon(
                key: const Key('submit_analysis'),
                onPressed: state.canSubmit
                    ? () async {
                        debounce?.cancel();
                        await widget.vm.setDraft(input.text);
                        await widget.vm.submit(input.text);
                      }
                    : null,
                icon: const Icon(Icons.auto_graph),
                label: Text(
                  state.phase == ScreenPhase.submitting ? '正在提交…' : '开始分析',
                ),
              ),
              if (state.hasPending)
                OutlinedButton(
                  onPressed: state.busy ? null : widget.vm.refresh,
                  child: const Text('恢复原请求'),
                ),
              if (state.problem != null)
                _Problem(state.problem!, onRetry: widget.vm.refresh),
              if (run != null) ...[
                const Divider(height: 32),
                Text(
                  _status(run.status),
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                Text(
                  _connection(state.connection),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                SelectableText(
                  '任务 ${run.id}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                if (!run.terminal) ...[
                  const SizedBox(height: 8),
                  if (state.connection == LiveConnection.connecting ||
                      state.connection == LiveConnection.online)
                    const LinearProgressIndicator(),
                  TextButton(
                    onPressed: state.busy
                        ? null
                        : () => widget.vm.openRun(run.id),
                    child: const Text('重新读取任务状态'),
                  ),
                ],
                if (run.steps.isNotEmpty)
                  Card(
                    child: Column(
                      children: [
                        for (final step in run.steps)
                          ListTile(
                            dense: true,
                            leading: Icon(
                              step['status'] == 'completed'
                                  ? Icons.check_circle_outline
                                  : Icons.hourglass_top,
                            ),
                            title: Text(_node(step['node'].toString())),
                            trailing: Text(
                              step['status'] == 'completed' ? '完成' : '进行中',
                            ),
                          ),
                      ],
                    ),
                  ),
                if (run.structured != null)
                  _StructuredResult(run.structured!)
                else if (run.answer.isNotEmpty)
                  _TextCard('分析结论', run.answer),
                if (run.toJson()['_error'] != null)
                  _TextCard('运行说明', run.toJson()['_error'].toString()),
                if (run.terminal &&
                    run.answer.isEmpty &&
                    run.structured == null)
                  const _TextCard('运行说明', '此任务没有生成完整结论。可保留该记录并发起新的分析。'),
                _EvidenceList(run.evidence),
              ],
            ],
          ),
        ),
      );
    },
  );
}

class _StructuredResult extends StatelessWidget {
  const _StructuredResult(this.data);
  final Json data;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (data['summary'] != null) _TextCard('结论', _display(data['summary'])),
      if ((data['metrics'] as List? ?? []).isNotEmpty)
        _TextCard('指标', (data['metrics'] as List).map(_display).join('\n')),
      if (data['diagnosis'] != null && _display(data['diagnosis']).isNotEmpty)
        _TextCard('原因分析', _display(data['diagnosis'])),
      if ((data['recommended_actions'] as List? ?? []).isNotEmpty)
        _TextCard(
          '建议下一步',
          (data['recommended_actions'] as List)
              .asMap()
              .entries
              .map((entry) => '${entry.key + 1}. ${_display(entry.value)}')
              .join('\n\n'),
        ),
      if (data['experiment'] is Map && (data['experiment'] as Map).isNotEmpty)
        _TextCard('经营实验', _display(data['experiment'])),
      if ((data['limitations'] as List? ?? []).isNotEmpty)
        _TextCard(
          '适用范围',
          (data['limitations'] as List).map(_display).join('\n'),
        ),
      if ((data['assumptions'] as List? ?? []).isNotEmpty)
        _TextCard(
          '分析假设',
          (data['assumptions'] as List).map(_display).join('\n'),
        ),
      if ((data['memory_refs'] as List? ?? []).isNotEmpty)
        _TextCard(
          '本次使用的经营信息',
          (data['memory_refs'] as List).map(_display).join('\n'),
        ),
    ],
  );
}

class _MemoryPage extends StatelessWidget {
  const _MemoryPage(this.vm);
  final MerchantViewModel vm;
  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(20),
    children: [
      Text('经营信息', style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 8),
      const Text('确认信息后，后续分析可在适用范围内引用。待确认内容不会自动成为已确认事实。'),
      const SizedBox(height: 12),
      if (vm.state.memories.isEmpty) const Text('暂无经营信息。分析后可刷新查看待确认内容。'),
      for (final item in vm.state.memories)
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Chip(label: Text(_memoryStatus(item.status))),
                    const Spacer(),
                    Text(
                      'v${item.version}',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
                Text(
                  item.summary,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                if (item.factType.isNotEmpty) Text('类型：${item.factType}'),
                if (item.effectiveFrom != null)
                  Text(
                    '有效期：${item.effectiveFrom} — ${item.effectiveTo ?? '持续有效'}',
                  ),
                if (item.sourceEventId != null)
                  ExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: const Text('查看来源'),
                    children: [SelectableText(item.sourceEventId!)],
                  ),
                if (item.status == 'pending')
                  Wrap(
                    spacing: 8,
                    children: [
                      FilledButton(
                        onPressed: vm.state.memoryBusy.contains(item.id)
                            ? null
                            : () => vm.decide(item, true),
                        child: const Text('确认'),
                      ),
                      OutlinedButton(
                        onPressed: vm.state.memoryBusy.contains(item.id)
                            ? null
                            : () => vm.decide(item, false),
                        child: const Text('拒绝'),
                      ),
                    ],
                  ),
                if (vm.state.memoryBusy.contains(item.id))
                  const LinearProgressIndicator(),
              ],
            ),
          ),
        ),
      if (vm.state.moreMemories)
        TextButton(
          onPressed: () => vm.refreshMemories(more: true),
          child: const Text('加载更多'),
        ),
    ],
  );
}

class _SettingsPage extends StatefulWidget {
  const _SettingsPage(this.vm, {super.key});
  final MerchantViewModel vm;
  @override
  State<_SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<_SettingsPage> {
  late final url = TextEditingController(
    text: widget.vm.settings.baseUrl.toString(),
  );
  late final token = TextEditingController(
    text: widget.vm.settings.accessToken,
  );
  bool saving = false;
  @override
  void dispose() {
    url.dispose();
    token.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(20),
    children: [
      Text('连接设置', style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 12),
      const Text(
        '模拟器：http://10.0.2.2:8000\nUSB 调试设备：先配置 adb reverse，再使用 http://127.0.0.1:8000。正式构建仅接受 HTTPS。',
      ),
      const SizedBox(height: 20),
      TextField(
        key: const Key('server_url'),
        controller: url,
        keyboardType: TextInputType.url,
        decoration: const InputDecoration(labelText: '服务地址'),
      ),
      const SizedBox(height: 12),
      TextField(
        key: const Key('access_token'),
        controller: token,
        obscureText: true,
        autocorrect: false,
        enableSuggestions: false,
        decoration: const InputDecoration(labelText: 'Demo access token'),
      ),
      const SizedBox(height: 12),
      FilledButton(
        onPressed: saving
            ? null
            : () async {
                setState(() => saving = true);
                await widget.vm.updateSettings(url.text, token.text);
                if (mounted) setState(() => saving = false);
              },
        child: Text(saving ? '正在保存…' : '保存并连接'),
      ),
      const SizedBox(height: 16),
      const Text(
        'Token 由 Android Keystore 加密保存。任务和概览保存在本机 SQLite；服务端记录决定任务最终状态。',
        style: TextStyle(fontSize: 12),
      ),
      const SizedBox(height: 12),
      const Text(
        '这是受控合成数据的工程演示，未接入真实商家账户或电商写操作。',
        style: TextStyle(fontSize: 12),
      ),
    ],
  );
}

class _Problem extends StatelessWidget {
  const _Problem(this.problem, {required this.onRetry});
  final ApiFailure problem;
  final VoidCallback onRetry;
  @override
  Widget build(BuildContext context) => Card(
    color: Theme.of(context).colorScheme.errorContainer,
    child: Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${_problemLabel(problem.problem)}：${problem.message}'),
          if (problem.retryable || problem.problem == RequestProblem.conflict)
            TextButton(onPressed: onRetry, child: const Text('恢复 / 刷新状态')),
        ],
      ),
    ),
  );
}

class _TextCard extends StatelessWidget {
  const _TextCard(this.title, this.text);
  final String title;
  final String text;
  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 8),
          SelectableText(text),
        ],
      ),
    ),
  );
}

class _EvidenceList extends StatelessWidget {
  const _EvidenceList(this.items);
  final List<EvidenceItem> items;
  @override
  Widget build(BuildContext context) => items.isEmpty
      ? const SizedBox.shrink()
      : Card(
          child: ExpansionTile(
            title: Text('证据与来源 · ${items.length}'),
            leading: const Icon(Icons.fact_check_outlined),
            children: [
              for (final item in items)
                ListTile(
                  title: SelectableText(item.text),
                  subtitle: item.id.isEmpty ? null : SelectableText(item.id),
                ),
            ],
          ),
        );
}

String _date(DateTime value) => value.toIso8601String().substring(0, 10);
String _display(dynamic value) {
  if (value == null) return '';
  if (value is List) return value.map(_display).join('\n');
  if (value is Map) {
    if (value.containsKey('label') && value.containsKey('value'))
      return '${value['label']}：${value['value']} ${value['unit'] ?? ''}';
    return value.entries
        .map((entry) => '${entry.key}：${_display(entry.value)}')
        .join('\n');
  }
  return value.toString();
}

String _status(String value) => switch (value) {
  'queued' => '等待分析',
  'running' => '分析中',
  'completed' => '分析完成',
  'failed' => '分析失败',
  'interrupted' => '任务已中断',
  'cancelled' => '已取消',
  _ => value,
};
String _memoryStatus(String value) => switch (value) {
  'pending' => '待确认',
  'approved' || 'active' => '已确认',
  'rejected' => '已拒绝',
  'superseded' => '已更新',
  _ => value,
};
String _connection(LiveConnection value) => switch (value) {
  LiveConnection.online => '已同步服务端状态',
  LiveConnection.connecting => '正在连接',
  LiveConnection.interrupted => '连接中断，保留最近状态',
  LiveConnection.offline => '本地缓存，等待同步',
};
String _problemLabel(RequestProblem value) => switch (value) {
  RequestProblem.unauthorised => '鉴权失败',
  RequestProblem.rateLimited => '演示额度限制',
  RequestProblem.timeout => '请求超时',
  RequestProblem.network => '连接问题',
  RequestProblem.server => '服务错误',
  RequestProblem.conflict => '状态已变化',
  RequestProblem.data => '数据校验失败',
  RequestProblem.storage => '本地保存问题',
};
String _node(String value) => switch (value) {
  'router' => '理解经营问题',
  'recall' => '回顾经营信息',
  'skill_discovery' => '查找分析方法',
  'skill_selection' => '选择分析方法',
  'planner' => '制定分析步骤',
  'executor' => '执行数据分析',
  'insight' => '整理结论',
  'memory_candidate' => '整理待确认信息',
  'memory_recall' || 'memory' => '读取适用经营信息',
  'skill_select' || 'skill' => '选择分析步骤',
  'metric' => '查询指标',
  'attribution' => '分析变化原因',
  'strategy' => '整理经营建议',
  'synthesis' => '汇总结论',
  'verifier' => '核对证据',
  _ => value,
};
