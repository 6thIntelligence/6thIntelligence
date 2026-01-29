import asyncio
import json
import time
import os
import sys
from uuid import uuid4

# Add project root to path
sys.path.append(os.getcwd())

from baselines.standard_rag import StandardRAG
from app.main import CausalFractalRAG

BENCHMARK_DIR = "data/benchmark"
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

def load_benchmark_dataset():
    conversations = []
    conv_dir = os.path.join(BENCHMARK_DIR, "conversations")
    if not os.path.exists(conv_dir):
        print("Benchmark dataset not found. Run scripts/generate_benchmark_dataset.py first.")
        return []
        
    for f in sorted(os.listdir(conv_dir)):
        if f.endswith(".json"):
            with open(os.path.join(conv_dir, f), 'r') as file:
                conversations.append(json.load(file))
    return conversations

def save_json(data, path):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

async def run_single_conversation(system, conversation_data):
    """Run one conversation through the system"""
    session_id = str(uuid4())
    results = {
        "context_sizes": [],
        "latencies": [],
        "responses": [],
        "retrieved_chunks": [] 
    }
    
    is_baseline = isinstance(system, StandardRAG)
    
    for turn in conversation_data["turns"]:
        start_time = time.time()
        
        # Handle method signature differences if any
        if is_baseline:
            response = await system.chat(query=turn["user_message"], session_id=session_id)
        else:
            response = await system.chat(query=turn["user_message"], session_id=session_id)
        
        latency = time.time() - start_time
        
        # Get context size (approx number of words/tokens)
        context = system.get_current_context()
        context_size = len(context.split())
        
        results["context_sizes"].append(context_size)
        results["latencies"].append(latency)
        results["responses"].append(response)
        # results["retrieved_chunks"].append(...) # If system exposes this
    
    return results

async def main():
    conversations = load_benchmark_dataset()
    if not conversations:
        return

    print(f"Loaded {len(conversations)} conversations.")
    
    baseline_results = []
    causal_results = []
    
    # Limit to subset for quick verify if needed, or run all 50
    # For full paper, run all.
    for conv in conversations[:5]: # Running 5 for brevity in this check, user can change to all
        print(f"Running conversation {conv['id']}")
        
        # Re-init systems for each conversation to clear state
        baseline = StandardRAG()
        causal_fractal = CausalFractalRAG()
        
        b_res = await run_single_conversation(baseline, conv)
        baseline_results.append(b_res)
        
        c_res = await run_single_conversation(causal_fractal, conv)
        causal_results.append(c_res)
        
    save_json(baseline_results, os.path.join(RESULTS_DIR, "baseline_raw.json"))
    save_json(causal_results, os.path.join(RESULTS_DIR, "causal_fractal_raw.json"))
    
    print("Experiments complete!")

if __name__ == "__main__":
    asyncio.run(main())
