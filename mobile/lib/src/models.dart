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
  const SseEvent(this.type, this.data);

  final SseEventType type;
  final String data;
}

class ClientSettings {
  const ClientSettings({required this.baseUrl, required this.accessToken});

  final Uri baseUrl;
  final String accessToken;

  bool get isConfigured => baseUrl.hasScheme && accessToken.isNotEmpty;
}

enum RequestProblem { unauthorised, rateLimited, timeout, network, server }

class MemoryItem {
  const MemoryItem({required this.id, required this.status, required this.summary});

  final String id;
  final String status;
  final String summary;

  MemoryItem withStatus(String value) =>
      MemoryItem(id: id, status: value, summary: summary);
}
