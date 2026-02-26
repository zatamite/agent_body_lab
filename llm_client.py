"""
llm_client.py — Wraps the Google GenAI SDK for designing the robot chassis.
"""
import os
from google import genai
from google.genai import types

def get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")
    return genai.Client(api_key=api_key)

def generate_blender_script(prompt: str) -> str:
    """
    Sends a prompt to Gemini 2.5 Flash and extracts the Python response.
    Expects prompt to instruct the model to return a Blender Python script.
    """
    client = get_client()
    
    # We use gemini-2.5-pro for complex coding, flash is also great but pro is better for API usage
    print("🧠 Prompting Gemini for CAD generation...")
    response = client.models.generate_content(
        model='gemini-2.5-pro',
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
        )
    )
    
    text = response.text
    
    # Extract python code block if present
    if "```python" in text:
        return text.split("```python")[1].split("```")[0].strip()
    elif "```" in text:
        return text.split("```")[1].split("```")[0].strip()
        
    return text.strip()

if __name__ == "__main__":
    # Test connection if key is present
    if os.environ.get("GEMINI_API_KEY"):
        print("API Key found. Testing connection...")
        try:
            client = get_client()
            res = client.models.generate_content(
                model='gemini-2.5-flash',
                contents="Write a 1-line python script that prints 'Hello Chassis'"
            )
            print("Response:", res.text.strip())
        except Exception as e:
            print("Error connecting to Gemini:", e)
    else:
        print("Please set GEMINI_API_KEY to test the connection.")
