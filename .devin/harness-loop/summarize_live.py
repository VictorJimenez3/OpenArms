"""One line per request from live_app_check.py output (stdin)."""
import json
import sys

buffer, decoder, index = sys.stdin.read(), json.JSONDecoder(), 0
while (start := buffer.find('{', index)) >= 0:
    row, index = decoder.raw_decode(buffer, start)
    print(f"{row['route']:<12} {row['status']:<19} proposal {row['request_to_proposal_s']:>6}s  answer {row['request_to_result_s']:>6}s"
          f"  calls {row['model_calls']}  {row['fast_path']} | {row['text'][:60]}")
