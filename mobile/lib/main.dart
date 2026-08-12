import 'package:flutter/material.dart';

import 'src/controller.dart';
import 'src/models.dart';

void main() => runApp(const MerchantCopilotApp());

class MerchantCopilotApp extends StatelessWidget {
  const MerchantCopilotApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'MerchantCopilot v2',
        home: Scaffold(
          appBar: AppBar(title: const Text('MerchantCopilot v2')),
          body: const _ClientHome(),
        ),
      );
}

class _ClientHome extends StatefulWidget {
  const _ClientHome();

  @override
  State<_ClientHome> createState() => _ClientHomeState();
}

class _ClientHomeState extends State<_ClientHome> {
  final controller = TimelineController(const [
    MemoryItem(id: 'demo-pending', status: 'pending', summary: '待确认的经营约束'),
  ]);

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('参考客户端核心：Android 工程、安全存储和 APK 构建在 T11 验收前补齐。'),
          const SizedBox(height: 16),
          const Text('Memory Timeline'),
          for (final item in controller.items)
            ListTile(
              title: Text(item.summary),
              subtitle: Text(item.status),
              trailing: item.status == 'pending'
                  ? Wrap(children: [
                      IconButton(
                        tooltip: '批准',
                        onPressed: () => setState(() => controller.applyDecision(item.id, true)),
                        icon: const Icon(Icons.check),
                      ),
                      IconButton(
                        tooltip: '拒绝',
                        onPressed: () => setState(() => controller.applyDecision(item.id, false)),
                        icon: const Icon(Icons.close),
                      ),
                    ])
                  : null,
            ),
        ],
      );
}
