import chromadb
from chromadb.utils import embedding_functions
import os

# Initialize Chroma Client with persistence
CHROMA_PATH = "data/chroma_db"
os.makedirs("data", exist_ok=True)

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

# Use a standard, fast local embedding model
embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

# Get or create collection
collection = chroma_client.get_or_create_collection(
    name="enterprise_kb",
    embedding_function=embedding_fn
)

def add_document(doc_id: str, text: str, metadata: dict):
    """
    Split text into chunks and add to vector store.
    """
    # Improved chunking: try to split at newlines
    chunk_size = 1000
    overlap = 100
    
    chunks = []
    ids = []
    metadatas = []
    
    start = 0
    text_len = len(text)
    last_start = -1
    
    while start < text_len:
        end = min(start + chunk_size, text_len)
        
        # If we are not at the end of text, try to find a newline to break at
        if end < text_len:
            # Look for the last newline within the chunk
            # We search back from 'end'
            last_newline = text.rfind('\n', start, end)
            if last_newline != -1 and last_newline > start + chunk_size // 2:
                # If we found a newline reasonably far into the chunk, use it
                end = last_newline + 1 # Include the newline
            
        chunk = text[start:end]
        chunks.append(chunk)
        ids.append(f"{doc_id}_{start}")
        metadatas.append(metadata)
        
        if end >= text_len:
            break
            
        # Move start pointer for overlap
        next_start = end - overlap
        
        # Ensure we always advance at least 1 char
        if next_start <= last_start:
             next_start = last_start + 1
             
        # Also ensure we don't go backwards if end was shortened significantly (unlikely with logic above but safe)
        if next_start <= start:
             # Should not happen given overlap < chunk/2, but safety net
             next_start = start + 1
             
        start = next_start
        last_start = start
        
    if chunks:
        # ChromaDB has a maximum batch size (usually 5461)
        # We use a safe batch size of 5000
        batch_size_limit = 5000
        for i in range(0, len(chunks), batch_size_limit):
            batch_chunks = chunks[i:i + batch_size_limit]
            batch_ids = ids[i:i + batch_size_limit]
            batch_metadatas = metadatas[i:i + batch_size_limit]
            
            collection.add(
                documents=batch_chunks,
                ids=batch_ids,
                metadatas=batch_metadatas
            )

def query_knowledge(query_text: str, n_results: int = 5):
    """
    Search for relevant documents in vector store.
    """
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results
    )
    
    # Return formatted context string
    context = ""
    if results['documents']:
        for doc_list in results['documents']:
            for doc in doc_list:
                context += f"{doc}\n---\n"
    return context

import asyncio
from concurrent.futures import ThreadPoolExecutor

# Create a thread pool for blocking operations
executor = ThreadPoolExecutor(max_workers=3)

async def query_knowledge_async(query_text: str, n_results: int = 5):
    """
    Search for relevant documents in vector store asynchronously.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, query_knowledge, query_text, n_results)

def delete_document(doc_id: str):
    """
    Remove all chunks associated with a document ID.
    """
    # Since IDs are prefixed with doc_id, we can filter by metadata
    collection.delete(where={"source_id": doc_id})
