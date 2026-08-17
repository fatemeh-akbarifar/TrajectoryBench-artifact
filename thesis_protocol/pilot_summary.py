import json
import glob

# Find latest run file
files = glob.glob("outputs/**/*.jsonl", recursive=True)

if not files:
    print("No runs.jsonl found")
    exit()

file = files[-1]
print(f"Using file: {file}")

total = 0
success = 0
steps_list = []

with open(file, "r") as f:
    for line in f:
        total += 1
        data = json.loads(line)

        # Try common fields (AgentBench varies)
        if "result" in data:
            if str(data["result"]).lower() in ["true", "success", "1"]:
                success += 1

        if "steps" in data:
            steps_list.append(data["steps"])

# Basic stats
print("\n--- Pilot Summary ---")
print(f"Total episodes: {total}")
print(f"Success count: {success}")

if total > 0:
    print(f"Success rate: {success/total:.2f}")

if steps_list:
    print(f"Avg steps: {sum(steps_list)/len(steps_list):.2f}")
