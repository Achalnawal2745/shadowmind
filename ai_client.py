from google import genai
from google.genai import types

SYSTEM_PROMPT = """You are a concise expert interview assistant.
When given an interview question:
- Understand questions in English, Hindi, or Hinglish.
- Give a direct, confident answer in first person.
- If the question is in Hindi/Hinglish, you may respond in English (standard for tech interviews) or Hinglish if it sounds more natural, but prioritize professional English for technical answers.
- Use short bullet points for technical questions.
- ALWAYS wrap code snippets in standard markdown code blocks (```python, ```cpp, etc.).
- Keep answers under 120 words.
- Start answering immediately — no preamble.
"""

MAX_HISTORY = 10  # Keep last 10 exchanges (20 messages) to stay within token limits


class GeminiClient:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.history = []  # List of {"role": "user"/"model", "parts": [...]}

    def clear_history(self):
        self.history = []

    def stream(self, question: str, image_bytes: bytes = None):
        """Yields text chunks as Gemini generates the answer (supports text or image)."""
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
        )

        # Build the user message parts
        user_parts = [types.Part.from_text(text=question)]
        if image_bytes:
            user_parts.append(types.Part.from_bytes(data=image_bytes, mime_type='image/png'))

        # Add user message to history
        self.history.append({"role": "user", "parts": user_parts})

        # Trim history to avoid exceeding token limits (keep last MAX_HISTORY pairs)
        if len(self.history) > MAX_HISTORY * 2:
            self.history = self.history[-(MAX_HISTORY * 2):]

        # Build contents from full history
        contents = [
            types.Content(role=msg["role"], parts=msg["parts"])
            for msg in self.history
        ]

        response = self.client.models.generate_content_stream(
            model='gemini-2.5-flash',
            contents=contents,
            config=config
        )

        # Collect full answer while streaming
        full_answer = []
        for chunk in response:
            if chunk.text:
                full_answer.append(chunk.text)
                yield chunk.text

        # Save model response to history
        if full_answer:
            self.history.append({
                "role": "model",
                "parts": [types.Part.from_text(text=''.join(full_answer))]
            })
