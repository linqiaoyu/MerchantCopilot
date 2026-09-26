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
      expect(
        parseSseLines(['event: ${entry.key}', 'data: {}', '']).single.type,
        entry.value,
      );
    });
  }

  test('ignores an unknown event', () {
    expect(parseSseLines(['event: future', 'data: {}', '']), isEmpty);
  });

  test('joins multi-line data', () {
    expect(
      parseSseLines(['event: token', 'data: a', 'data: b', '']).single.data,
      'a\nb',
    );
  });

  test('parses a streamed event boundary', () async {
    final stream = Stream<String>.fromIterable([
      'event: final',
      'data: {"answer":"ok"}',
      '',
    ]);
    final events = await parseSseStream(stream).toList();
    expect(events.single.type, SseEventType.finalAnswer);
    expect(events.single.data, '{"answer":"ok"}');
  });

  test('does not consume an unterminated frame after disconnect', () async {
    final events = await parseSseStream(
      Stream.fromIterable([
        'id: 12',
        'event: final',
        'data: {"run_id":"r1","answer":"partial"}',
      ]),
    ).toList();
    expect(events, isEmpty);
  });

  test('retains numeric event cursor and ignores heartbeat comments', () async {
    final events = await parseSseStream(
      Stream.fromIterable([
        ': keepalive',
        '',
        'id: 4',
        'event: node_started',
        'data: {"run_id":"r1","node":"metric"}',
        '',
      ]),
    ).toList();
    expect(events.single.id, 4);
  });
}
