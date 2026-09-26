import 'models.dart';

/// 只有空行结束的完整帧才能落库；断流残帧不推进游标。
class _FrameParser {
  String? name;
  int? id;
  final data = <String>[];
  int size = 0;

  SseEvent? add(String line) {
    size += line.length;
    if (size > 1024 * 1024) throw const FormatException('SSE frame too large');
    if (line.isEmpty) {
      final type = name == null ? null : parseEventType(name!);
      final event = type == null || data.isEmpty
          ? null
          : SseEvent(type, data.join('\n'), id: id);
      name = null;
      id = null;
      data.clear();
      size = 0;
      return event;
    }
    if (line.startsWith(':')) return null;
    if (line.startsWith('event:')) name = line.substring(6).trim();
    if (line.startsWith('id:')) {
      id = int.tryParse(line.substring(3).trim());
      if (id == null || id! < 0)
        throw const FormatException('Invalid SSE cursor');
    }
    if (line.startsWith('data:'))
      data.add(line.substring(5).replaceFirst(RegExp(r'^ '), ''));
    return null;
  }
}

Iterable<SseEvent> parseSseLines(Iterable<String> lines) sync* {
  final parser = _FrameParser();
  for (final line in lines) {
    final event = parser.add(line);
    if (event != null) yield event;
  }
}

Stream<SseEvent> parseSseStream(Stream<String> lines) async* {
  final parser = _FrameParser();
  await for (final line in lines) {
    final event = parser.add(line);
    if (event != null) yield event;
  }
}
