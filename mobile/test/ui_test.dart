import 'dart:io';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:merchant_copilot/main.dart';
import 'package:merchant_copilot/src/local_store.dart';
import 'package:merchant_copilot/src/models.dart';
import 'package:merchant_copilot/src/view_model.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'view_model_test.dart' show ControlledGateway, MemoryTokenStore;

void main() {
  sqfliteFfiInit();

  testWidgets(
    'compact screen exposes overview, restored task, evidence and pending memory without overflow',
    (tester) async {
      tester.view.physicalSize = const Size(360, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      late Directory directory;
      late LocalStore store;
      late MerchantViewModel vm;
      await tester.runAsync(() async {
        directory = await Directory.systemTemp.createTemp('merchant-ui-');
        store = await LocalStore.open(
          factory: databaseFactoryFfi,
          path: '${directory.path}/client.db',
        );
        final api = ControlledGateway()
          ..run = {
            'run_id': 'r1',
            'thread_id': 't1',
            'status': 'completed',
            'query': '分析成交金额',
            'result': '成交金额为 12500 元',
            'structured_result': {
              'kind': 'metric',
              'summary': '成交金额为 12500 元',
              'metrics': [],
              'recommended_actions': ['继续观察下个周期'],
              'evidence': [
                {'id': 'synthetic:gmv', 'text': '合成经营账本'},
              ],
              'limitations': ['仅适用于演示数据'],
              'memory_refs': [],
            },
          };
        vm = MerchantViewModel(
          store: store,
          tokenStore: MemoryTokenStore(),
          gatewayFactory: (_) => api,
        );
        await vm.initialize(remote: false);
        await vm.repository.createAnalysis('分析成交金额');
        var eventId = 0;
        for (final node in [
          'recall',
          'skill_discovery',
          'skill_selection',
          'planner',
          'executor',
          'insight',
          'memory_candidate',
        ]) {
          await store.applyEvent(
            vm.repository.scope,
            'r1',
            SseEvent(
              SseEventType.nodeStarted,
              jsonEncode({'run_id': 'r1', 'node': node}),
              id: ++eventId,
            ),
          );
          await store.applyEvent(
            vm.repository.scope,
            'r1',
            SseEvent(
              SseEventType.nodeCompleted,
              jsonEncode({'run_id': 'r1', 'node': node}),
              id: ++eventId,
            ),
          );
        }
        await vm.openRun('r1');
        await vm.refreshOverview();
        await vm.refreshMemories();
        await vm.refreshHistory();
      });
      await tester.pumpWidget(MerchantCopilotApp(viewModel: vm));
      await tester.pumpAndSettle();
      expect(find.text('看清变化，再做决定'), findsOneWidget);
      expect(find.text('成交金额'), findsOneWidget);
      expect(tester.takeException(), isNull);

      expect(find.widgetWithText(NavigationDestination, '设置'), findsNothing);
      expect(find.byType(NavigationDestination), findsNWidgets(3));
      await tester.tap(find.byKey(const Key('open_settings')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('server_url')), findsOneWidget);
      expect(find.byType(NavigationBar), findsNothing);
      await tester.pageBack();
      await tester.pumpAndSettle();

      await tester.tap(find.text('记录').last);
      await tester.pumpAndSettle();
      expect(find.text('分析成交金额'), findsOneWidget);
      await tester.tap(find.text('概览').last);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('提出经营问题'));
      await tester.tap(find.text('提出经营问题'));
      await tester.pumpAndSettle();
      expect(find.text('经营分析'), findsOneWidget);
      expect(find.text('分析完成'), findsOneWidget);
      await tester.drag(find.byType(ListView).first, const Offset(0, -500));
      await tester.pumpAndSettle();
      expect(find.text('回顾经营信息'), findsOneWidget);
      expect(find.text('整理待确认信息'), findsOneWidget);
      expect(find.text('skill_discovery'), findsNothing);
      expect(tester.takeException(), isNull);

      await tester.pageBack();
      await tester.pumpAndSettle();
      await tester.tap(find.text('经营信息').last);
      await tester.pumpAndSettle();
      expect(find.text('毛利率目标 40%'), findsOneWidget);
      expect(find.text('待确认'), findsOneWidget);
      expect(find.text('确认'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('概览').last);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('成交金额'));
      await tester.tap(find.text('成交金额'));
      await tester.runAsync(() async {
        await Future<void>.delayed(const Duration(milliseconds: 80));
      });
      await tester.pumpAndSettle();
      expect(vm.state.draft, contains('GMV是否下跌'));
      expect(vm.state.draft, contains('未下跌则说明数据'));
      expect(vm.state.context!['metric'], 'gmv');
      expect(vm.state.run, isNull); // 新问题不混入上一项已完成任务的结论。
      expect(find.text('分析完成'), findsNothing);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.runAsync(() async {
        await vm.suspend();
        vm.dispose();
        await store.close();
        await directory.delete(recursive: true);
      });
    },
  );
}
