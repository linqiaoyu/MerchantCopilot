"""Generate a separate diagnostic MainActivity; never edit the ordinary source.

Build the generated source with tool/keystore_queue_acceptance.dart only in a
diagnostic APK. The normal MainActivity contains no delay or diagnostic channel.
Run once with the saved pre-fix source and once with the fixed source. This
isolates the Keystore threading risk; it does not identify the earlier ANR cause.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


SETUP = """
        // Diagnostic APK only: main Looper heartbeat and injected slow I/O.
        val probeHandler = android.os.Handler(android.os.Looper.getMainLooper())
        val probeEvents = java.util.Collections.synchronizedList(mutableListOf<Map<String, Any>>())
        var probeStarted = android.os.SystemClock.elapsedRealtime()
        var probeLastBeat = probeStarted
        var probeBeats = 0
        var probeMaxGap = 0L
        val probeTicker = object : Runnable {
            override fun run() {
                val now = android.os.SystemClock.elapsedRealtime()
                probeMaxGap = maxOf(probeMaxGap, now - probeLastBeat)
                probeLastBeat = now
                probeBeats += 1
                if (now - probeStarted < 120000L) probeHandler.postDelayed(this, 25L)
            }
        }
        probeHandler.post(probeTicker)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "merchantcopilot/token_store_diagnostic")
            .setMethodCallHandler { probeCall, probeResult ->
                when (probeCall.method) {
                    "reset", "snapshot" -> {
                        if (probeCall.method == "reset") {
                            probeStarted = android.os.SystemClock.elapsedRealtime()
                            probeLastBeat = probeStarted
                            probeBeats = 0
                            probeMaxGap = 0L
                            probeEvents.clear()
                        }
                        val probeNow = android.os.SystemClock.elapsedRealtime()
                        probeResult.success(mapOf(
                            "variant" to "__VARIANT__",
                            "source_sha256" to "__SOURCE_SHA__",
                            "delay_ms" to __DELAY__,
                            "absolute_wall_limit_ms" to 120000,
                            "heartbeat_interval_ms" to 25,
                            "heartbeat_count" to probeBeats,
                            "main_looper_max_gap_ms" to maxOf(probeMaxGap, probeNow - probeLastBeat),
                            "elapsed_ms" to (probeNow - probeStarted),
                            "events" to synchronized(probeEvents) { probeEvents.toList() },
                        ))
                    }
                    "stop" -> {
                        probeHandler.removeCallbacks(probeTicker)
                        probeResult.success(null)
                    }
                    else -> probeResult.notImplemented()
                }
            }
"""


def generate(source: str, *, delay_ms: int, variant: str) -> str:
    if variant not in {"before", "after"} or not 1 <= delay_ms <= 10000:
        raise ValueError("invalid diagnostic variant or delay")
    if "merchantcopilot/token_store_diagnostic" in source:
        raise ValueError("source is already instrumented")
    setup_anchor = "        super.configureFlutterEngine(flutterEngine)\n"
    handler_anchor = "setMethodCallHandler { call, result ->\n            try {\n"
    catch_anchor = '                result.error("keystore_failure", "Unable to access Android Keystore", error.javaClass.simpleName)\n            }\n'
    for anchor in (setup_anchor, handler_anchor, catch_anchor):
        if source.count(anchor) != 1:
            raise ValueError("MainActivity changed: expected exactly one diagnostic insertion anchor")
    setup = SETUP.replace("__DELAY__", str(delay_ms)).replace("__VARIANT__", variant)
    setup = setup.replace("__SOURCE_SHA__", hashlib.sha256(source.encode()).hexdigest())
    source = source.replace(setup_anchor, setup_anchor + setup)
    source = source.replace(handler_anchor, """setMethodCallHandler { call, result ->
            probeEvents.add(mapOf("method" to call.method, "phase" to "start",
                "on_main" to (android.os.Looper.myLooper() == android.os.Looper.getMainLooper())))
            try {
                Thread.sleep(__DELAY__L)
""".replace("__DELAY__", str(delay_ms)))
    return source.replace(catch_anchor, catch_anchor.rstrip("\n") + """ finally {
                probeEvents.add(mapOf("method" to call.method, "phase" to "end",
                    "on_main" to (android.os.Looper.myLooper() == android.os.Looper.getMainLooper())))
            }
""")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", choices=("before", "after"), required=True)
    parser.add_argument("--delay-ms", type=int, default=1200)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("output must be a separate diagnostic copy")
    if not 1 <= args.delay_ms <= 10000:
        parser.error("delay must be within 1..10000 ms")
    generated = generate(args.source.read_text(), delay_ms=args.delay_ms, variant=args.variant)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        handle.write(generated)
    print(args.output)


if __name__ == "__main__":
    main()
