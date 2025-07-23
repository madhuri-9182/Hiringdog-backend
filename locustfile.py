from locust import HttpUser, task, between

class InterviewUser(HttpUser):
    wait_time = between(1, 3)  # seconds between tasks

    @task
    def schedule_interview(self):
        self.client.post("/api/schedule/", json={
            "candidate_id": 123,
            "interviewer_id": 456,
            "time": "2024-07-18T10:00:00Z"
        })