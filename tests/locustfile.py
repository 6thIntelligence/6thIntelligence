"""
Locust Load Testing Configuration for Enterprise Bot
Run with: locust -f tests/locustfile.py --host=http://localhost:8000
"""
from locust import HttpUser, task, between, events
import json
import uuid
import random

# Sample messages for testing
SAMPLE_MESSAGES = [
    "What properties are available in Lagos?",
    "I'm looking for a 3-bedroom apartment in Lekki",
    "What's the average rent in Ikoyi?",
    "Can you help me find a house to buy?",
    "How does ExpertListing verify listings?",
    "I want to rent a property in Victoria Island",
    "What areas have the best rental prices?",
    "Tell me about property inspection services",
    "Are there any studio apartments available?",
    "What documents do I need to rent a property?",
]

class ChatUser(HttpUser):
    """
    Simulates a user interacting with the chatbot.
    """
    wait_time = between(1, 3)  # Wait 1-3 seconds between requests
    
    def on_start(self):
        """Called when user starts - create a new session"""
        self.session_id = str(uuid.uuid4())
        self.conversation_history = []
    
    @task(5)
    def send_chat_message(self):
        """Send a chat message - most common action"""
        message = random.choice(SAMPLE_MESSAGES)
        
        self.conversation_history.append({
            "role": "user",
            "content": message
        })
        
        payload = {
            "messages": self.conversation_history
        }
        
        with self.client.post(
            f"/api/chat?session_id={self.session_id}",
            json=payload,
            headers={"Content-Type": "application/json"},
            name="/api/chat",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                # Add assistant response to history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response.text[:500]  # Truncate for memory
                })
                response.success()
            elif response.status_code == 429:
                response.failure("Rate limited")
            else:
                response.failure(f"Status: {response.status_code}")
        
        # Keep conversation history manageable
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-6:]
    
    @task(2)
    def start_new_session(self):
        """Start a new chat session"""
        self.session_id = str(uuid.uuid4())
        self.conversation_history = []
        
        # Get the chat page
        with self.client.get("/", name="Homepage", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")
    
    @task(1)
    def view_chat_history(self):
        """View chat history for current session"""
        with self.client.get(
            f"/api/chat/history/{self.session_id}",
            name="/api/chat/history",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")

class AdminUser(HttpUser):
    """
    Simulates an admin user checking dashboard stats.
    Runs less frequently than chat users.
    """
    wait_time = between(5, 10)
    weight = 1  # Lower weight means fewer admin users
    
    def on_start(self):
        """Login as admin"""
        # Note: In real testing, you'd authenticate properly
        self.token = None
    
    @task(2)
    def view_dashboard_stats(self):
        """Check dashboard stats"""
        # Would need authentication in real scenario
        with self.client.get(
            "/api/admin/stats",
            name="/api/admin/stats",
            catch_response=True
        ) as response:
            # Expect 401 without auth, that's ok for load testing
            if response.status_code in [200, 401]:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")
    
    @task(1)
    def view_sessions(self):
        """View all chat sessions"""
        with self.client.get(
            "/api/chat/sessions",
            name="/api/chat/sessions",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")

class MixedUser(HttpUser):
    """
    Simulates typical user behavior with a mix of actions.
    This is the primary user type for realistic load testing.
    """
    wait_time = between(2, 5)
    weight = 3  # Most common user type
    
    def on_start(self):
        self.session_id = str(uuid.uuid4())
        self.messages = []
    
    @task(10)
    def typical_conversation(self):
        """Simulate a typical conversation flow"""
        # Start or continue conversation
        message = random.choice(SAMPLE_MESSAGES)
        self.messages.append({"role": "user", "content": message})
        
        payload = {"messages": self.messages}
        
        with self.client.post(
            f"/api/chat?session_id={self.session_id}",
            json=payload,
            name="/api/chat",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                self.messages.append({
                    "role": "assistant",
                    "content": response.text[:200]
                })
                response.success()
            elif response.status_code == 429:
                response.failure("Rate limited")
            else:
                response.failure(f"Error: {response.status_code}")
        
        # Reset after a few messages
        if len(self.messages) > 8:
            self.session_id = str(uuid.uuid4())
            self.messages = []
    
    @task(2)
    def submit_feedback(self):
        """Submit feedback for session"""
        payload = {
            "session_id": self.session_id,
            "rating": random.randint(3, 5),  # Mostly positive
            "category": random.choice(["response_quality", "speed", "helpfulness"]),
            "comment": random.choice([None, "Good response", "Very helpful"])
        }
        
        with self.client.post(
            "/api/feedback",
            json=payload,
            name="/api/feedback",
            catch_response=True
        ) as response:
            if response.status_code in [200, 500]:  # 500 if feedback service not ready
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")

# Event handlers for custom reporting
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Log request metrics"""
    if response_time > 2000:  # Log slow requests (>2s)
        print(f"SLOW REQUEST: {request_type} {name} took {response_time}ms")

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts"""
    print("Load test starting...")
    print(f"Target host: {environment.host}")

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops"""
    print("Load test completed.")
    
    # Print summary
    stats = environment.runner.stats
    print(f"\nTotal requests: {stats.total.num_requests}")
    print(f"Failed requests: {stats.total.num_failures}")
    print(f"Average response time: {stats.total.avg_response_time:.2f}ms")
    print(f"95th percentile: {stats.total.get_response_time_percentile(0.95):.2f}ms")
