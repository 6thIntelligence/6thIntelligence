"""
Cache Service for Enterprise Bot
Provides in-memory caching for frequent queries
"""
import time
import hashlib
from typing import Optional, Dict, Any
from collections import OrderedDict
import threading

class LRUCache:
    """Thread-safe LRU Cache implementation"""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: OrderedDict = OrderedDict()
        self.timestamps: Dict[str, float] = {}
        self.ttls: Dict[str, int] = {}
        self.lock = threading.Lock()
        self.hits = 0
        self.misses = 0
    
    def _generate_key(self, query: str) -> str:
        """Generate cache key from query"""
        return hashlib.md5(query.encode()).hexdigest()
    
    def _is_expired(self, key: str) -> bool:
        """Check if entry is expired"""
        if key not in self.timestamps:
            return True
        ttl = self.ttls.get(key, self.default_ttl)
        return (time.time() - self.timestamps[key]) > ttl
    
    def _cleanup_expired(self):
        """Remove expired entries (called periodically)"""
        expired = [k for k in self.cache if self._is_expired(k)]
        for k in expired:
            self._remove(k)
    
    def _remove(self, key: str):
        """Remove entry from cache"""
        if key in self.cache:
            del self.cache[key]
        if key in self.timestamps:
            del self.timestamps[key]
        if key in self.ttls:
            del self.ttls[key]
    
    def get(self, query: str) -> Optional[str]:
        """Get cached response for query"""
        key = self._generate_key(query)
        
        with self.lock:
            if key not in self.cache:
                self.misses += 1
                return None
            
            if self._is_expired(key):
                self._remove(key)
                self.misses += 1
                return None
            
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            self.hits += 1
            return self.cache[key]
    
    def set(self, query: str, response: str, ttl: int = None):
        """Cache response for query"""
        key = self._generate_key(query)
        
        with self.lock:
            # Remove if exists
            if key in self.cache:
                self._remove(key)
            
            # Evict oldest if at capacity
            while len(self.cache) >= self.max_size:
                oldest = next(iter(self.cache))
                self._remove(oldest)
            
            # Add new entry
            self.cache[key] = response
            self.timestamps[key] = time.time()
            self.ttls[key] = ttl or self.default_ttl
    
    def invalidate(self, pattern: str = None):
        """
        Invalidate cache entries.
        If pattern is None, clear entire cache.
        """
        with self.lock:
            if pattern is None:
                self.cache.clear()
                self.timestamps.clear()
                self.ttls.clear()
            else:
                # Pattern-based invalidation
                keys_to_remove = [
                    k for k in self.cache 
                    if pattern in str(self.cache[k])
                ]
                for k in keys_to_remove:
                    self._remove(k)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate_percent": round(hit_rate, 2),
                "memory_estimate_kb": sum(len(str(v)) for v in self.cache.values()) // 1024
            }
    
    def reset_stats(self):
        """Reset hit/miss counters"""
        with self.lock:
            self.hits = 0
            self.misses = 0

# Global cache instance
_cache = LRUCache(max_size=500, default_ttl=3600)  # 1 hour TTL

def cache_response(query: str, response: str, ttl: int = 3600):
    """Cache a response for a query"""
    _cache.set(query, response, ttl)

def get_cached_response(query: str) -> Optional[str]:
    """Get cached response for a query"""
    return _cache.get(query)

def invalidate_cache(pattern: str = None):
    """Invalidate cache entries (None = clear all)"""
    _cache.invalidate(pattern)

def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics"""
    return _cache.get_stats()

def should_cache(query: str) -> bool:
    """
    Determine if a query should be cached.
    Some queries are too specific/personal to cache.
    """
    query_lower = query.lower()
    
    # Don't cache personal/specific queries
    no_cache_patterns = [
        "my ", "i am", "i'm", "my name",
        "call me", "phone", "email",
        "today", "now", "current"
    ]
    
    for pattern in no_cache_patterns:
        if pattern in query_lower:
            return False
    
    # Don't cache very short queries
    if len(query) < 10:
        return False
    
    # Cache common property queries
    cache_patterns = [
        "how much", "what is", "where is",
        "rent", "buy", "property", "area",
        "location", "price", "bedroom"
    ]
    
    for pattern in cache_patterns:
        if pattern in query_lower:
            return True
    
    return False

def get_or_set(query: str, compute_func, ttl: int = 3600) -> str:
    """
    Get cached response or compute and cache.
    compute_func should return the response string.
    """
    cached = get_cached_response(query)
    if cached is not None:
        return cached
    
    response = compute_func()
    if should_cache(query):
        cache_response(query, response, ttl)
    
    return response

# Semantic cache for similar queries (optional enhancement)
class SemanticCache:
    """
    Cache that can match semantically similar queries.
    Uses simple string similarity for now.
    """
    
    def __init__(self, similarity_threshold: float = 0.85):
        self.threshold = similarity_threshold
        self.cache: Dict[str, str] = {}
        self.lock = threading.Lock()
    
    def _similarity(self, s1: str, s2: str) -> float:
        """Calculate simple string similarity"""
        s1, s2 = s1.lower().split(), s2.lower().split()
        if not s1 or not s2:
            return 0.0
        
        common = set(s1) & set(s2)
        total = set(s1) | set(s2)
        
        return len(common) / len(total)
    
    def get(self, query: str) -> Optional[str]:
        """Get response for query or similar query"""
        with self.lock:
            # Exact match
            if query in self.cache:
                return self.cache[query]
            
            # Similarity match
            for cached_query, response in self.cache.items():
                if self._similarity(query, cached_query) >= self.threshold:
                    return response
        
        return None
    
    def set(self, query: str, response: str):
        """Cache response"""
        with self.lock:
            self.cache[query] = response
            
            # Limit size
            if len(self.cache) > 200:
                # Remove oldest (first) entries
                keys = list(self.cache.keys())[:50]
                for k in keys:
                    del self.cache[k]
    
    def clear(self):
        """Clear cache"""
        with self.lock:
            self.cache.clear()

# Optional semantic cache instance
semantic_cache = SemanticCache()
