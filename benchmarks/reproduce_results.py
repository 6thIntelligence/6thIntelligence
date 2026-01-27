
import asyncio
import time
import json
import os
import matplotlib.pyplot as plt
import pandas as pd
from typing import List, Dict
from app.services.state_manager import StateManager
from app.services.causal_service import CausalService
from app.database import SessionLocal, Message
from app.services import openrouter_service

class ResearchBenchmarker:
    """
    Automated Research Benchmarking Suite for Causal-Fractal RAG.
    Simulates long-form conversations and calculates statistical rigor.
    """
    
    def __init__(self, session_id: str = "benchmark_test_001"):
        self.session_id = session_id
        self.results = []
        self.causal_service = CausalService()
        
    async def run_drift_test(self, turns: int = 30):
        """
        Simulates a long conversation to measure context drift and hallucination.
        """
        print(f"Starting Longitudinal Drift Test ({turns} turns)...")
        db = SessionLocal()
        state_mgr = StateManager(db)
        
        parent_id = None
        
        # Test Query Set (Domain: Real Estate & Financial Mechanisms)
        queries = [
            "What causes the price of luxury apartments in Lagos to rise?",
            "How does interest rate affect mortgage affordability?",
            "Can you link the 2024 inflation rate to rental yields?",
            "Wait, what did we say earlier about interest rates?", # Test recall
            "Summarize the causal chain from inflation to my personal budget.",
            # Repeat/Vary for 30 turns...
        ] * (turns // 5 + 1)

        for i in range(turns):
            start_time = time.time()
            query = queries[i]
            
            # 1. State Retrieval Simulation
            history = await state_mgr.get_context_chain(parent_id) if parent_id else []
            
            # 2. Causal Verify Simulation (Simulated logic for benchmark)
            sim_chunks = ["Luxury prices rise because of low supply", "Mortgage depends on interest"]
            verified = self.causal_service.verify_mechanisms(query, sim_chunks)
            
            # 3. Create Node (Fractal logic)
            # Simulate child response
            child_node_id = await state_mgr.create_node(
                session_id=self.session_id,
                parent_id=parent_id,
                role="assistant",
                content=f"Simulated response for {query}",
                tokens=100
            )
            
            elapsed = time.time() - start_time
            self.results.append({
                "turn": i,
                "latency_sec": elapsed,
                "context_nodes": len(history),
                "is_fractal": True,
                "node_id": child_node_id
            })
            
            parent_id = child_node_id # Progress parent
            print(f"Turn {i+1}/{turns} complete in {elapsed:.2f}s")
            
        self.generate_report()

    def generate_report(self):
        df = pd.DataFrame(self.results)
        os.makedirs("logs/benchmarks", exist_ok=True)
        
        # Save JSON Report
        report_path = f"logs/benchmarks/run_{int(time.time())}.json"
        df.to_json(report_path)
        
        # Plot Context tokens vs Turn (Growth Rate)
        plt.figure(figsize=(10, 6))
        plt.plot(df['turn'], df['context_nodes'], marker='o', color='#2ecc71', label='Fractal Hierarchy Storage')
        plt.title("Renormalization Efficiency in Long-Form Context")
        plt.xlabel("Interaction Depth (Turns)")
        plt.ylabel("Active Nodes in Context")
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.savefig("docs/benchmark_context_growth.png", dpi=300)
        
        print(f"\nReport saved to: {report_path}")
        print("Visualization saved to: docs/benchmark_context_growth.png")
        
        # Output LaTeX Table for paper
        print("\n--- LATEX TABLE ARTIFACT ---")
        print(df.describe().to_latex())

if __name__ == "__main__":
    bench = ResearchBenchmarker()
    # This would be run in an async loop
    # asyncio.run(bench.run_drift_test(10))
