set -e
cd /Users/victor/OpenArms/harness-loop-v2
run() { PYTHONPATH=agentic:. /Users/victor/OpenArms/device-expert-smoke/.venv-lab/bin/python agentic/scripts/harness_benchmark.py run --target /Users/victor/OpenArms/harness-checkpoint-v2 --revision 0287c6e35f36c2f690ccbb6104bf146e1570aa61 --guarded --modes end-to-end --temperatures cold --repeats 2 --expert live --reasoning-effort medium "$@"; }
run --out outputs/tier-std-D01 --select D01 > outputs/tier-std-D01.log
run --out outputs/tier-pri-D01 --select D01 --service-tier priority > outputs/tier-pri-D01.log
run --out outputs/tier-std-H01 --cases .devin/harness-loop/heldout.jsonl --select H01 > outputs/tier-std-H01.log
run --out outputs/tier-pri-H01 --cases .devin/harness-loop/heldout.jsonl --select H01 --service-tier priority > outputs/tier-pri-H01.log
echo TIER_DONE
