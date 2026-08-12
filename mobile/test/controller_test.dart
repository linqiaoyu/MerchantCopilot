import 'package:flutter_test/flutter_test.dart';
import 'package:merchant_copilot/src/controller.dart';
import 'package:merchant_copilot/src/models.dart';

void main() {
  test('approving pending memory updates its timeline state', () {
    final controller = TimelineController(const [MemoryItem(id: 'a', status: 'pending', summary: 'x')]);
    controller.applyDecision('a', true);
    expect(controller.items.single.status, 'approved');
  });

  test('rejecting pending memory updates its timeline state', () {
    final controller = TimelineController(const [MemoryItem(id: 'a', status: 'pending', summary: 'x')]);
    controller.applyDecision('a', false);
    expect(controller.items.single.status, 'rejected');
  });

  test('401 maps to an actionable client problem', () {
    expect(TimelineController([]).classifyStatus(401), RequestProblem.unauthorised);
  });

  test('429 maps to an actionable client problem', () {
    expect(TimelineController([]).classifyStatus(429), RequestProblem.rateLimited);
  });

  test('server failures map to an actionable client problem', () {
    expect(TimelineController([]).classifyStatus(503), RequestProblem.server);
  });
}
