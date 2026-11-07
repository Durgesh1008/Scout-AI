
from app.services.llm import generate, check_connection

print("Checking Ollama...")

if check_connection():
    print("Ollama connected successfully!")

    answer = generate(
        "Explain resume-based job matching in three points."
    )

    print("\nAI Response:")
    print(answer)
else:
    print("Ollama connection failed. Check your configuration.")
