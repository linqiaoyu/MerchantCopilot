import 'models.dart';

/// 只接受服务端固定的 11 种事件；未知事件不会影响既有会话状态。
Iterable<SseEvent> parseSseLines(Iterable<String> lines) sync* {
  String? eventName;
  final data = <String>[];

  void reset() {
    eventName = null;
    data.clear();
  }

  for (final line in lines) {
    if (line.isEmpty) {
      final type = eventName == null ? null : parseEventType(eventName!);
      if (type != null) yield SseEvent(type, data.join('\n'));
      reset();
    } else if (line.startsWith('event:')) {
      eventName = line.substring(6).trim();
    } else if (line.startsWith('data:')) {
      data.add(line.substring(5).trimLeft());
    }
  }
  final type = eventName == null ? null : parseEventType(eventName!);
  if (type != null) yield SseEvent(type, data.join('\n'));
}
