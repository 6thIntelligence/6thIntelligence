
import spacy
import networkx as nx
import os
import json
import logging
from pathlib import Path
from sqlalchemy.orm import Session
from app.database import SessionLocal, KnowledgeDoc
from app.services.causal_service import CausalService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def build_graph():
    """
    Analyzes the Knowledge Base and builds a causal graph by extracting 'X causes Y' patterns.
    """
    causal_service = CausalService()
    if not causal_service.nlp:
        logger.error("Spacy model not found. Run: python -m spacy download en_core_web_md")
        return

    db = SessionLocal()
    docs = db.query(KnowledgeDoc).all()
    
    logger.info(f"Processing {len(docs)} documents for causal links...")
    
    causal_verbs = ["lead to", "leads to", "caused", "causes", "resulted in", "results in", "triggered", "triggers", "produced", "produces"]
    
    for doc in docs:
        text = doc.content
        if not text: continue
        
        # Process in chunks to avoid MemoryError
        chunk_size = 50000
        for i in range(0, len(text), chunk_size):
            chunk_text = text[i:i + chunk_size]
            nlp_doc = causal_service.nlp(chunk_text)
            
            for sent in nlp_doc.sents:
                sent_text = sent.text.lower()
                for verb in causal_verbs:
                    if verb in sent_text:
                        # (triplet extraction logic stays same)
                        parts = sent_text.split(verb)
                        if len(parts) == 2:
                            cause_text = parts[0].strip()
                            effect_text = parts[1].strip()
                            
                            # Extract key entities from cause and effect
                            # Use smaller nlp call for entities
                            cause_entities = [ent.text for ent in causal_service.nlp(cause_text).ents] or [cause_text.split()[-1]]
                            effect_entities = [ent.text for ent in causal_service.nlp(effect_text).ents] or [effect_text.split()[0]]
                            
                            for c in cause_entities:
                                for e in effect_entities:
                                    if len(c) > 2 and len(e) > 2:
                                        logger.info(f"Adding causal link: {c} -> {e}")
                                        causal_service.graph.add_edge(c.lower(), e.lower(), mechanism=verb, source_doc=doc.id)

    causal_service.save_graph()
    db.close()
    logger.info("Causal graph construction complete.")

if __name__ == "__main__":
    build_graph()
