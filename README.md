# Causal-Fractal RAG

Implementation of "Hierarchical Context Management with Causal Verification for Long-Form RAG: A Renormalization Group Approach"

arXiv: [2502.XXXXX]

## Installation
```bash
git clone https://github.com/yourusername/causal-fractal-rag
cd causal-fractal-rag
pip install -r requirements.txt
python scripts/build_causal_graph.py  # Takes ~8 hours
```

## Quick Start
```python
from app.main import CausalFractalRAG
import asyncio

async def main():
    system = CausalFractalRAG()
    # Ensure you have set OPENROUTER_API_KEY in environment or settings.json
    response = await system.chat("What are the causes of the 2008 financial crisis?", session_id="demo_session")
    print(response)

# asyncio.run(main())
```

## Reproduce Paper Results
```bash
# 1. Generate benchmark dataset
python scripts/generate_benchmark_dataset.py


# 2. Run experiments (Simulates 50 conversations x 40 turns)
python experiments/run_benchmark.py

# 3. Compute metrics and generate LaTeX table
python experiments/evaluate.py

# 4. Generate modern research visualizations
python scripts/modern_viz.py

# Results saved to results/metrics_summary.json, results/metrics_summary.tex and docs/paper_artifacts/
```

## Visualizations
The system includes an advanced plotting suite for research communications:
- **Scaling Laws**: Logarithmic context growth vs linear baselines.
- **Stability Analysis**: Violin plots showing hallucination suppression.
- **Radar Charts**: Multi-dimensional system capability profiling.
- **Pareto Frontiers**: Quality-latency tradeoff analysis.

## Citation
```bibtex
@article{adewuyi2025causal,
  title={Hierarchical Context Management with Causal Verification for Long-Form RAG},
  author={Adewuyi, Abayomi Daniel},
  journal={arXiv preprint arXiv:XXXX.XXXXX},
  year={2025}
}
```
