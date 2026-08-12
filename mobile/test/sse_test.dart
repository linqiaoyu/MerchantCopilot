import 'package:flutter_test/flutter_test.dart';
import 'package:merchant_copilot/src/models.dart';
import 'package:merchant_copilot/src/sse.dart';

void main() {
  for (final entry in <String, SseEventType>{
    'meta': SseEventType.meta,
    'node_started': SseEventType.nodeStarted,
    'node_completed': SseEventType.nodeCompleted,
    'tool_call': SseEventType.toolCall,
    'evidence': SseEventType.evidence,
    'memory_recalled': SseEventType.memoryRecalled,
    'memory_candidate': SseEventType.memoryCandidate,
    'token': SseEventType.token,
    'final': SseEventType.finalAnswer,
    'error': SseEventType.error,
    'done': SseEventType.done,
  }.entries) {
    test('parses ${entry.key}', () {
      expect(parseSseLines(['event: ${entry.key}', 'data: {}', '']).single.type, entry.value);
    });
  }

  test('ignores an unknown event', () {
    expect(parseSseLines(['event: future', 'data: {}', '']), isEmpty);
  });

  test('joins multi-line data', () {
    expect(parseSseLines(['event: token', 'data: a', 'data: b', '']).single.data, 'a\nb');
  });
}
