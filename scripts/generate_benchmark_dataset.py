import json
import os
import random
from typing import List, Dict

benchmark_dir = "data/benchmark"
conversations_dir = os.path.join(benchmark_dir, "conversations")
ground_truth_dir = os.path.join(benchmark_dir, "ground_truth")

os.makedirs(conversations_dir, exist_ok=True)
os.makedirs(ground_truth_dir, exist_ok=True)

def generate_conversation(conversation_id: int, num_turns: int = 40) -> Dict:
    """
    Generates a synthetic conversation.
    """
    topic = random.choice(["Housing Crisis", "Inflation", "Tech Support", "Medical Diagnosis", "Legal Dispute"])
    
    turns = []
    for i in range(num_turns):
        turns.append({
            "turn_id": i,
            "role": "user",
            "user_message": f"Question {i} regarding {topic} details."
        })
        
    conversation = {
        "id": f"conv_{conversation_id:03d}",
        "topic": topic,
        "turns": turns
    }
    return conversation

def generate_ground_truth(conversation_id: int) -> Dict:
    """
    Generates dummy ground truth for metrics calculation.
    """
    return {
        "conversation_id": f"conv_{conversation_id:03d}",
        "ground_truth": {
            "causal_edges": [
                {
                    "source": "cause_A", 
                    "target": "effect_B", 
                    "mentioned_in_turn": 5, 
                    "required_for_turn": 10
                }
            ],
            "entities": [
                {
                    "entity": "Entity_X",
                    "first_mention": 2,
                    "should_be_consistent_in": [2, 10, 20, 39]
                }
            ],
            "hallucination_checks": [
                {
                    "turn": 15,
                    "expected_fact": "Fact X is True",
                    "hallucination_if_says": ["Fact X is False"]
                }
            ]
        }
    }

if __name__ == "__main__":
    print(f"Generating 50 benchmark conversations in {benchmark_dir}...")
    
    for i in range(50):
        # 1. Conversation
        conv = generate_conversation(i)
        with open(os.path.join(conversations_dir, f"conv_{i:03d}.json"), "w") as f:
            json.dump(conv, f, indent=2)
            
        # 2. Ground Truth
        gt = generate_ground_truth(i)
        with open(os.path.join(ground_truth_dir, f"conv_{i:03d}.json"), "w") as f:
            json.dump(gt, f, indent=2)
            
    print("Dataset generation complete.")
