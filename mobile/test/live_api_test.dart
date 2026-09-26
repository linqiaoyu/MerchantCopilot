import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:merchant_copilot/src/api_client.dart';
import 'package:merchant_copilot/src/models.dart';

/// 显式 opt-in 的只读 HTTP 联调，不提交收费的分析请求。
void main() {
  final configPath = Platform.environment['MERCHANT_RUNTIME_CONFIG'];
  test(
    'local backend returns overview, run history and typed memories for the Flutter client',
    () async {
      final config =
          jsonDecode(await File(configPath!).readAsString())
              as Map<String, dynamic>;
      final api = MerchantApi(
        ClientSettings(
          baseUrl: Uri.parse(config['base_url'] as String),
          accessToken: config['access_token'] as String,
        ),
      );
      addTearDown(api.close);
      final overview = await api.getOverview('', '');
      expect(overview['synthetic'], isTrue);
      expect(overview['metrics'], isNotEmpty);
      expect(
        DateTime.tryParse(overview['available_from'].toString()),
        isNotNull,
      );
      expect(DateTime.tryParse(overview['available_to'].toString()), isNotNull);
      for (final item in overview['evidence'] as List) {
        expect(EvidenceItem.fromJson(item).id, isNotEmpty);
      }
      final history = await api.listRuns();
      for (final item in history['items'] as List) {
        expect(
          RunRecord(Map<String, dynamic>.from(item as Map)).id,
          isNotEmpty,
        );
      }
      final memories = await api.listMemories();
      for (final item in memories['items'] as List) {
        expect(
          MemoryItem.fromJson(Map<String, dynamic>.from(item as Map)).version,
          greaterThanOrEqualTo(1),
        );
      }
    },
    skip: configPath == null
        ? 'Requires MERCHANT_RUNTIME_CONFIG; read-only backend smoke is opt-in.'
        : false,
  );
}
