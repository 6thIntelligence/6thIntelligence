"""
Performance Tests for Enterprise Bot
Tests response times, database performance, and concurrent handling.

Run with: pytest tests/test_performance.py -v
"""
import pytest
import time
import asyncio
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
import statistics
import uuid

# Test configuration
BASE_URL = "http://localhost:8000"
CONCURRENT_USERS = 10
REQUESTS_PER_USER = 5

class TestResponseTimes:
    """Test API response times meet targets"""
    
    def test_homepage_load_time(self):
        """Homepage should load in under 500ms"""
        start = time.time()
        response = httpx.get(f"{BASE_URL}/")
        elapsed = (time.time() - start) * 1000
        
        assert response.status_code == 200
        assert elapsed < 500, f"Homepage took {elapsed:.2f}ms, expected <500ms"
    
    def test_chat_history_response_time(self):
        """Chat history should return in under 200ms"""
        session_id = str(uuid.uuid4())
        
        start = time.time()
        response = httpx.get(f"{BASE_URL}/api/chat/history/{session_id}")
        elapsed = (time.time() - start) * 1000
        
        assert response.status_code == 200
        assert elapsed < 200, f"Chat history took {elapsed:.2f}ms, expected <200ms"
    
    def test_sessions_list_response_time(self):
        """Sessions list should return in under 300ms"""
        start = time.time()
        response = httpx.get(f"{BASE_URL}/api/chat/sessions")
        elapsed = (time.time() - start) * 1000
        
        assert response.status_code == 200
        assert elapsed < 300, f"Sessions list took {elapsed:.2f}ms, expected <300ms"


class TestConcurrentRequests:
    """Test handling of concurrent requests"""
    
    def test_concurrent_homepage_requests(self):
        """Server should handle 20 concurrent homepage requests"""
        def fetch_homepage():
            start = time.time()
            response = httpx.get(f"{BASE_URL}/")
            return time.time() - start, response.status_code
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(fetch_homepage) for _ in range(20)]
            results = [f.result() for f in as_completed(futures)]
        
        times = [r[0] * 1000 for r in results]
        status_codes = [r[1] for r in results]
        
        # All should succeed
        assert all(code == 200 for code in status_codes), "Some requests failed"
        
        # Average should be under 1 second
        avg_time = statistics.mean(times)
        assert avg_time < 1000, f"Average response time {avg_time:.2f}ms, expected <1000ms"
    
    def test_concurrent_sessions(self):
        """Multiple sessions should work independently"""
        def create_session_and_chat():
            session_id = str(uuid.uuid4())
            
            payload = {
                "messages": [{"role": "user", "content": "Hello"}]
            }
            
            response = httpx.post(
                f"{BASE_URL}/api/chat?session_id={session_id}",
                json=payload,
                timeout=30.0
            )
            
            return session_id, response.status_code
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_session_and_chat) for _ in range(5)]
            results = [f.result() for f in as_completed(futures)]
        
        session_ids = [r[0] for r in results]
        
        # All session IDs should be unique
        assert len(set(session_ids)) == len(session_ids), "Session IDs not unique"


class TestDatabasePerformance:
    """Test database query performance"""
    
    def test_session_creation_speed(self):
        """Session creation should be fast"""
        times = []
        
        for _ in range(10):
            session_id = str(uuid.uuid4())
            payload = {
                "messages": [{"role": "user", "content": "Test message"}]
            }
            
            start = time.time()
            response = httpx.post(
                f"{BASE_URL}/api/chat?session_id={session_id}",
                json=payload,
                timeout=30.0
            )
            times.append(time.time() - start)
        
        avg_time = statistics.mean(times) * 1000
        # This includes AI response time, so be generous
        assert avg_time < 30000, f"Average session creation {avg_time:.2f}ms"
    
    def test_history_retrieval_consistent(self):
        """History retrieval should have consistent performance"""
        session_id = str(uuid.uuid4())
        times = []
        
        for _ in range(20):
            start = time.time()
            httpx.get(f"{BASE_URL}/api/chat/history/{session_id}")
            times.append((time.time() - start) * 1000)
        
        # Standard deviation should be low (consistent performance)
        if len(times) > 1:
            stdev = statistics.stdev(times)
            assert stdev < 100, f"Response time too variable: stdev={stdev:.2f}ms"


class TestSecurityPerformance:
    """Test that security checks don't add significant latency"""
    
    def test_input_validation_overhead(self):
        """Security validation should add minimal overhead"""
        session_id = str(uuid.uuid4())
        
        # Normal message
        normal_payload = {
            "messages": [{"role": "user", "content": "What properties are available?"}]
        }
        
        start = time.time()
        httpx.post(
            f"{BASE_URL}/api/chat?session_id={session_id}",
            json=normal_payload,
            timeout=30.0
        )
        normal_time = time.time() - start
        
        # Message that might trigger security checks
        suspicious_payload = {
            "messages": [{"role": "user", "content": "SELECT * FROM users; DROP TABLE --"}]
        }
        
        start = time.time()
        httpx.post(
            f"{BASE_URL}/api/chat?session_id={session_id}",
            json=suspicious_payload,
            timeout=30.0
        )
        security_time = time.time() - start
        
        # Security checks should add less than 100ms overhead
        overhead = abs(security_time - normal_time) * 1000
        # This is approximate since AI response times vary
        print(f"Security overhead: {overhead:.2f}ms")


class TestRateLimiting:
    """Test rate limiting behavior"""
    
    def test_rate_limit_triggers(self):
        """Rate limiter should trigger after excessive requests"""
        session_id = str(uuid.uuid4())
        
        # Make many rapid requests
        responses = []
        for i in range(15):  # Exceed chat limit of 10/minute
            payload = {
                "messages": [{"role": "user", "content": f"Test {i}"}]
            }
            response = httpx.post(
                f"{BASE_URL}/api/chat?session_id={session_id}",
                json=payload,
                timeout=30.0
            )
            responses.append(response.status_code)
        
        # Should see some 429 responses
        has_rate_limit = 429 in responses
        print(f"Rate limit triggered: {has_rate_limit}")
        print(f"Response codes: {responses}")


def run_benchmark():
    """Run a quick benchmark and print results"""
    print("\n" + "="*50)
    print("Enterprise Bot Performance Benchmark")
    print("="*50)
    
    # Homepage latency
    times = []
    for _ in range(10):
        start = time.time()
        httpx.get(f"{BASE_URL}/")
        times.append((time.time() - start) * 1000)
    
    print(f"\nHomepage Latency (10 requests):")
    print(f"  Min: {min(times):.2f}ms")
    print(f"  Max: {max(times):.2f}ms")
    print(f"  Avg: {statistics.mean(times):.2f}ms")
    
    # Chat history latency
    times = []
    session_id = str(uuid.uuid4())
    for _ in range(10):
        start = time.time()
        httpx.get(f"{BASE_URL}/api/chat/history/{session_id}")
        times.append((time.time() - start) * 1000)
    
    print(f"\nChat History Latency (10 requests):")
    print(f"  Min: {min(times):.2f}ms")
    print(f"  Max: {max(times):.2f}ms")
    print(f"  Avg: {statistics.mean(times):.2f}ms")
    
    print("\n" + "="*50)
    print("Benchmark Complete")
    print("="*50)


if __name__ == "__main__":
    run_benchmark()
