import 'models.dart';

class TimelineController {
  TimelineController(this._items);

  List<MemoryItem> _items;
  List<MemoryItem> get items => List.unmodifiable(_items);

  void applyDecision(String id, bool approved) {
    _items = _items
        .map((item) => item.id == id
            ? item.withStatus(approved ? 'approved' : 'rejected')
            : item)
        .toList();
  }

  RequestProblem? classifyStatus(int statusCode) => switch (statusCode) {
        401 => RequestProblem.unauthorised,
        429 => RequestProblem.rateLimited,
        >= 500 => RequestProblem.server,
        _ => null,
      };
}
