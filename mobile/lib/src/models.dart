typedef Json = Map<String, dynamic>;

enum SseEventType {
  meta,
  nodeStarted,
  nodeCompleted,
  toolCall,
  evidence,
  memoryRecalled,
  memoryCandidate,
  token,
  finalAnswer,
  error,
  done,
}

SseEventType? parseEventType(String value) => switch (value) {
  'meta' => SseEventType.meta,
  'node_started' => SseEventType.nodeStarted,
  'node_completed' => SseEventType.nodeCompleted,
  'tool_call' => SseEventType.toolCall,
  'evidence' => SseEventType.evidence,
  'memory_recalled' => SseEventType.memoryRecalled,
  'memory_candidate' => SseEventType.memoryCandidate,
  'token' => SseEventType.token,
  'final' => SseEventType.finalAnswer,
  'error' => SseEventType.error,
  'done' => SseEventType.done,
  _ => null,
};

class SseEvent {
  const SseEvent(this.type, this.data, {this.id});

  final SseEventType type;
  final String data;
  final int? id;
}

class ClientSettings {
  const ClientSettings({required this.baseUrl, required this.accessToken});

  final Uri baseUrl;
  final String accessToken;

  bool get isConfigured => baseUrl.hasScheme && accessToken.isNotEmpty;

  ClientSettings copyWith({Uri? baseUrl, String? accessToken}) =>
      ClientSettings(
        baseUrl: baseUrl ?? this.baseUrl,
        accessToken: accessToken ?? this.accessToken,
      );
}

enum RequestProblem {
  unauthorised,
  rateLimited,
  timeout,
  network,
  server,
  conflict,
  data,
  storage,
}

class MemoryItem {
  const MemoryItem({
    required this.id,
    required this.status,
    required this.summary,
    this.version = 1,
    this.factType = '',
    this.effectiveFrom,
    this.effectiveTo,
    this.sourceEventId,
    this.indexStatus = '',
  });

  final String id;
  final String status;
  final String summary;
  final int version;
  final String factType;
  final String? effectiveFrom;
  final String? effectiveTo;
  final String? sourceEventId;
  final String indexStatus;

  factory MemoryItem.fromJson(Json data) => MemoryItem(
    id: data['memory_id'] as String,
    status: data['status'] as String? ?? 'unknown',
    summary: data['content'] as String? ?? '',
    version: (data['version'] as num?)?.toInt() ?? 1,
    factType: data['fact_type'] as String? ?? '',
    effectiveFrom: data['effective_from']?.toString(),
    effectiveTo: (data['effective_to'] ?? data['to'])?.toString(),
    sourceEventId: data['source_event_id']?.toString(),
    indexStatus: data['index_status'] as String? ?? '',
  );

  Json toJson() => {
    'memory_id': id,
    'status': status,
    'content': summary,
    'version': version,
    'fact_type': factType,
    'effective_from': effectiveFrom,
    'effective_to': effectiveTo,
    'source_event_id': sourceEventId,
    'index_status': indexStatus,
  };

  MemoryItem withStatus(String value) =>
      MemoryItem.fromJson({...toJson(), 'status': value});
}

class EvidenceItem {
  const EvidenceItem(this.text, {this.id = ''});

  final String text;
  final String id;

  factory EvidenceItem.fromJson(dynamic value) => value is Map
      ? EvidenceItem(
          (value['text'] ?? value['content'] ?? value).toString(),
          id: (value['id'] ?? value['source_ref'] ?? '').toString(),
        )
      : EvidenceItem(value.toString());
  Json toJson() => {'id': id, 'text': text};
}

class ApiFailure implements Exception {
  const ApiFailure(
    this.problem,
    this.message, {
    this.code = '',
    this.statusCode,
  });

  final RequestProblem problem;
  final String message;
  final String code;
  final int? statusCode;

  bool get retryable =>
      problem == RequestProblem.network ||
      problem == RequestProblem.timeout ||
      problem == RequestProblem.server;
  @override
  String toString() => message;
}

enum ScreenPhase { loading, ready, submitting, recovering, error }

enum LiveConnection { online, connecting, interrupted, offline }

class RunRecord {
  RunRecord(Json data) : _data = Map.unmodifiable(data) {
    if (data['run_id'] is! String ||
        data['thread_id'] is! String ||
        data['status'] is! String) {
      throw const FormatException('运行记录缺少必要字段');
    }
  }
  final Json _data;
  String get id => _data['run_id'] as String;
  String get threadId => _data['thread_id'] as String;
  String get query => _data['query'] as String? ?? '';
  String get status => _data['status'] as String;
  String get answer => (_data['result'] ?? _data['answer'] ?? '').toString();
  String get createdAt => _data['created_at']?.toString() ?? '';
  int get cursor => (_data['_cursor'] as num?)?.toInt() ?? 0;
  bool get terminal => const [
    'completed',
    'failed',
    'interrupted',
    'cancelled',
    'rejected',
  ].contains(status);
  List<Json> get steps => (_data['_steps'] as List? ?? [])
      .map((e) => Map<String, dynamic>.from(e as Map))
      .toList(growable: false);
  Json? get structured => _data['structured_result'] is Map
      ? Map<String, dynamic>.from(_data['structured_result'] as Map)
      : null;
  List<EvidenceItem> get evidence =>
      ((structured?['evidence'] ?? _data['_evidence']) as List? ?? [])
          .map(EvidenceItem.fromJson)
          .toList(growable: false);
  Json toJson() => Map<String, dynamic>.from(_data);
}
