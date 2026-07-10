from dotenv import load_dotenv
import os
result = load_dotenv()
key = os.getenv('ANTHROPIC_API_KEY')
print("load_dotenv returned:", result)
print("Key found:", repr(key))