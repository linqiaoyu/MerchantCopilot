import 'package:flutter/material.dart';

import 'src/models.dart';
import 'src/session.dart';

void main() => runApp(const MerchantCopilotApp());

class MerchantCopilotApp extends StatefulWidget {
  const MerchantCopilotApp({super.key});

  @override
  State<MerchantCopilotApp> createState() => _MerchantCopilotAppState();
}

class _MerchantCopilotAppState extends State<MerchantCopilotApp> {
  final session = ClientSession();
  int index = 0;

  @override
  void dispose() {
    session.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'MerchantCopilot v2',
        theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
        home: AnimatedBuilder(
          animation: session,
          builder: (context, _) => Scaffold(
            appBar: AppBar(title: const Text('MerchantCopilot v2')),
            body: IndexedStack(index: index, children: [
              _ChatPage(session),
              _EvidencePage(session.evidence),
              _MemoryPage(session),
              _SettingsPage(session),
            ]),
            bottomNavigationBar: NavigationBar(
              selectedIndex: index,
              onDestinationSelected: (value) => setState(() => index = value),
              destinations: const [
                NavigationDestination(icon: Icon(Icons.chat), label: 'Chat'),
                NavigationDestination(icon: Icon(Icons.fact_check), label: 'Evidence'),
                NavigationDestination(icon: Icon(Icons.history), label: 'Memory'),
                NavigationDestination(icon: Icon(Icons.settings), label: 'Settings'),
              ],
            ),
          ),
        ),
      );
}

class _ChatPage extends StatefulWidget {
  const _ChatPage(this.session);
  final ClientSession session;

  @override
  State<_ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<_ChatPage> {
  final input = TextEditingController();

  @override
  void dispose() {
    input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(widget.session.progress),
          if (widget.session.problemMessage != null)
            _ProblemBanner(problem: widget.session.problem, message: widget.session.problemMessage!),
          const SizedBox(height: 12),
          TextField(
            controller: input,
            minLines: 2,
            maxLines: 5,
            enabled: !widget.session.running,
            decoration: const InputDecoration(labelText: '经营问题', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: widget.session.running ? null : () => widget.session.submit(input.text),
            child: Text(widget.session.running ? '分析中…' : '开始分析'),
          ),
          if (widget.session.answer.isNotEmpty) ...[
            const SizedBox(height: 16),
            const Text('回答', style: TextStyle(fontWeight: FontWeight.bold)),
            SelectableText(widget.session.answer),
          ],
        ],
      );
}

class _EvidencePage extends StatelessWidget {
  const _EvidencePage(this.evidence);
  final List<EvidenceItem> evidence;

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(16),
        children: evidence.isEmpty
            ? const [Text('尚无本次运行的证据。')]
            : evidence.map((item) => ListTile(leading: const Icon(Icons.link), title: Text(item.text))).toList(),
      );
}

class _MemoryPage extends StatelessWidget {
  const _MemoryPage(this.session);
  final ClientSession session;

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          OutlinedButton.icon(
            onPressed: session.threadId == null ? null : session.refreshMemories,
            icon: const Icon(Icons.refresh),
            label: const Text('刷新 Timeline'),
          ),
          if (session.memories.isEmpty) const Text('当前 thread 尚无 Memory。'),
          for (final item in session.memories)
            ListTile(
              title: Text(item.summary),
              subtitle: Text(item.status),
              trailing: item.status == 'pending'
                  ? Wrap(children: [
                      IconButton(tooltip: '批准', onPressed: () => session.decide(item.id, true), icon: const Icon(Icons.check)),
                      IconButton(tooltip: '拒绝', onPressed: () => session.decide(item.id, false), icon: const Icon(Icons.close)),
                    ])
                  : null,
            ),
        ],
      );
}

class _SettingsPage extends StatefulWidget {
  const _SettingsPage(this.session);
  final ClientSession session;

  @override
  State<_SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<_SettingsPage> {
  late final TextEditingController url = TextEditingController(text: widget.session.settings.baseUrl.toString());
  late final TextEditingController token = TextEditingController(text: widget.session.settings.accessToken);

  @override
  void dispose() {
    url.dispose();
    token.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('本地模拟器使用 http://10.0.2.2:8000；Cloud Run 使用你的 HTTPS URL。'),
          const SizedBox(height: 12),
          TextField(controller: url, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'Base URL')),
          const SizedBox(height: 12),
          TextField(controller: token, obscureText: true, decoration: const InputDecoration(labelText: 'Demo access token')),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: () => widget.session.updateSettings(url.text, token.text),
            child: const Text('应用本次会话设置'),
          ),
          const SizedBox(height: 8),
          const Text('Token 目前仅保留在进程内；Android Keystore 安全持久化仍是 T11 未完成项。'),
        ],
      );
}

class _ProblemBanner extends StatelessWidget {
  const _ProblemBanner({required this.problem, required this.message});
  final RequestProblem? problem;
  final String message;

  @override
  Widget build(BuildContext context) => Card(
        color: Theme.of(context).colorScheme.errorContainer,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Text('${_label(problem)}：$message'),
        ),
      );

  String _label(RequestProblem? problem) => switch (problem) {
        RequestProblem.unauthorised => '401 鉴权失败',
        RequestProblem.rateLimited => '429 已达演示额度',
        RequestProblem.timeout => '请求超时',
        RequestProblem.network => '网络不可用',
        RequestProblem.server || null => '服务错误',
      };
}
