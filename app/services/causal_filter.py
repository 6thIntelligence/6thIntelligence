
import spacy
import networkx as nx
from typing import List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class CausalFilter:
    def __init__(self, graph_path: Path):
        self.graph_path = graph_path
        if graph_path.exists():
            with open(graph_path, 'r') as f:
                import json
                data = json.load(f)
                self.graph = nx.node_link_graph(data)
        else:
            self.graph = nx.DiGraph()
            
        try:
            self.nlp = spacy.load("en_core_web_md") # Use md/trf as available
        except:
            self.nlp = None
            logger.warning("Spacy model not found.")

    def extract_entities(self, text: str) -> List[str]:
        """Extract entities using spaCy NER"""
        if not self.nlp:
            return []
        doc = self.nlp(text)
        return [ent.text.lower() for ent in doc.ents] + [t.text.lower() for t in doc if t.pos_ in ["NOUN", "PROPN"]]
    
    def has_causal_path(self, query_entities: List[str], chunk_entities: List[str]) -> bool:
        """Check if directed path exists in graph"""
        for q_ent in query_entities:
            for c_ent in chunk_entities:
                if self.graph.has_node(q_ent) and self.graph.has_node(c_ent):
                    if nx.has_path(self.graph, q_ent, c_ent) or nx.has_path(self.graph, c_ent, q_ent):
                        return True
        return False
    
    def filter_chunks(self, query: str, chunks: List[str]) -> List[str]:
        """Return only causally-relevant chunks"""
        if not self.graph or not self.nlp:
            return chunks # Fallback
            
        query_entities = self.extract_entities(query)
        if not query_entities:
            return chunks
            
        relevant_chunks = []
        for chunk in chunks:
            chunk_entities = self.extract_entities(chunk)
            if self.has_causal_path(query_entities, chunk_entities):
                relevant_chunks.append(chunk)
                
        # If too restrictive, return original or top-k
        return relevant_chunks if relevant_chunks else chunks
