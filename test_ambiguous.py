import requests

cases = [
    "whats hot in Paris?",
    "how is London doing?",
    "is it cold outside?",
    "what is the capital of France?",
    "how much is a dozen eggs?",
    "what is Python?",
    "tell me about climate change",
    "2 apples plus 3 apples?",
]

for q in cases:
    r = requests.post("http://127.0.0.1:5000/api/chat", json={"session_id": "ambig-test", "message": q})
    d = r.json()
    dec = d.get("decision", "?")
    print(f"Q : {q}")
    print(f"-> {dec}")
    print()
