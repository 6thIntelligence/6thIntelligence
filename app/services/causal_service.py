
import spacy
import networkx as nx
import os
import json
import logging
from typing import List, Dict, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class CausalService:
    """
    Implements Causal Verification for RAG.
    Maintains a Causal Knowledge Graph and filters retrieved chunks based on causal mechanisms.
    """
    
    def __init__(self, graph_path: str = "data/causal_graph.json"):
        self.graph_path = graph_path
        self.graph = nx.DiGraph()
        try:
            self.nlp = spacy.load("en_core_web_md")
            self.nlp.max_length = 15000000 # Handle large research docs
        except:
            # Fallback if model not downloaded
            logger.warning("Spacy model en_core_web_md not found. Use 'python -m spacy download en_core_web_md'")
            self.nlp = None
            
        self.load_graph()

    def load_graph(self):
        """Loads the causal graph from disk."""
        if os.path.exists(self.graph_path):
            with open(self.graph_path, 'r') as f:
                data = json.load(f)
                self.graph = nx.node_link_graph(data)
            logger.info(f"Loaded causal graph with {self.graph.number_of_nodes()} nodes.")
        else:
            logger.info("No causal graph found. Initializing empty.")

    def save_graph(self):
        """Serializes the graph to JSON."""
        os.makedirs(os.path.dirname(self.graph_path), exist_ok=True)
        data = nx.node_link_data(self.graph)
        with open(self.graph_path, 'w') as f:
            json.dump(data, f)

    def verify_mechanisms(self, query: str, context_chunks: List[str]) -> List[str]:
        """
        Reranks/filters context chunks based on causal path verification.
        Prioritizes chunks that explain the 'Mechanism' behind the query entities.
        """
        if not self.nlp:
            return context_chunks[:3] # Fallback
            
        query_entities = self._extract_entities(query)
        if not query_entities:
            return context_chunks[:3]

        scored_chunks = []
        for chunk in context_chunks:
            chunk_entities = self._extract_entities(chunk)
            score = 0.0
            
            # Check for causal paths in the graph between query entities and chunk entities
            for q_ent in query_entities:
                for c_ent in chunk_entities:
                    if self.graph.has_node(q_ent) and self.graph.has_node(c_ent):
                        # If a path exists, the chunk is causally relevant
                        if nx.has_path(self.graph, q_ent, c_ent) or nx.has_path(self.graph, c_ent, q_ent):
                            score += 1.0
            
            scored_chunks.append((chunk, score))

        # Sort by causal score
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        return [c[0] for c in scored_chunks[:3]]

    def _extract_entities(self, text: str) -> List[str]:
        """Extracts key entities (concepts) for graph nodes."""
        if not self.nlp: return []
        doc = self.nlp(text)
        # Focus on Nouns and Proper Nouns as causal agents/effects
        return [ent.text.lower() for ent in doc.ents] + [token.lemma_.lower() for token in doc if token.pos_ in ["NOUN", "PROPN"]]

    def add_causal_link(self, cause: str, effect: str, mechanism: str = "causes"):
        """Adds a directed edge to the causal graph."""
        self.graph.add_edge(cause.lower(), effect.lower(), mechanism=mechanism)
        self.save_graph()
