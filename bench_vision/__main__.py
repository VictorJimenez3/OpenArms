"""One entry point; each module also runs independently."""
import runpy
import sys

COMMANDS = ("demo", "capture", "episode", "keyframes", "geometry", "skills", "benchmark", "policy", "adaptation", "outcomes")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python -m bench_vision {" + ",".join(COMMANDS) + "} [options]")
        print("Start offline: python -m bench_vision demo --out outputs/bench-demo")
        return
    command = sys.argv.pop(1)
    if command not in COMMANDS:
        raise SystemExit(f"Unknown command: {command}")
    runpy.run_module(f"bench_vision.{command}",run_name="__main__")


if __name__ == "__main__":
    main()
