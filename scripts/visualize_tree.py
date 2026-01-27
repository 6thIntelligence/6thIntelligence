
import networkx as nx
import matplotlib.pyplot as plt
from sqlalchemy.orm import Session
from app.database import SessionLocal, Message
import os

def visualize_session_tree(session_id: str, output_path: str = "docs/session_tree.png"):
    """
    Generates a hierarchical visualization of the conversation tree.
    Nodes are colored by similarity to parent.
    """
    db = SessionLocal()
    messages = db.query(Message).filter(Message.session_id == session_id).all()
    db.close()

    if not messages:
        print(f"No messages found for session {session_id}")
        return

    G = nx.DiGraph()
    labels = {}
    colors = []

    for msg in messages:
        G.add_node(msg.node_id)
        labels[msg.node_id] = f"{msg.role}\n{msg.content[:20]}..."
        if msg.parent_id:
            G.add_edge(msg.parent_id, msg.node_id, weight=msg.similarity_to_parent)
        
        # Color based on similarity (Green = High similarity/redundant, Blue = Dissimilar/New Info)
        colors.append(msg.similarity_to_parent)

    plt.figure(figsize=(12, 8))
    pos = nx.spring_layout(G) # In the paper we'll use a better hierarchical layout
    
    nodes = nx.draw_networkx_nodes(G, pos, node_color=colors, cmap=plt.cm.RdYlGn, node_size=2000, alpha=0.8)
    nx.draw_networkx_edges(G, pos, arrowstyle='->', arrowsize=20, edge_color='gray', alpha=0.5)
    nx.draw_networkx_labels(G, pos, labels, font_size=8)
    
    plt.colorbar(nodes, label="Similarity to Parent")
    plt.title(f"Fractal Tree Visualization - Session {session_id[:8]}")
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path)
    print(f"Visualization saved to {output_path}")

if __name__ == "__main__":
    # Test with the first session found in DB
    db = SessionLocal()
    first_session = db.query(Message).first()
    if first_session:
        visualize_session_tree(first_session.session_id)
    db.close()
