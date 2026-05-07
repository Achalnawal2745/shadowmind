from google import genai
from google.genai import types

SYSTEM_PROMPT = """You are a concise expert interview assistant.
When given an interview question:
- Understand questions in English, Hindi, or Hinglish.
- Give a direct, confident answer in first person.
- If the question is in Hindi/Hinglish, you may respond in English (standard for tech interviews) or Hinglish if it sounds more natural, but prioritize professional English for technical answers.
- Use short bullet points for technical questions.
- Keep answers under 120 words.
- Start answering immediately — no preamble.
"""


class GeminiClient:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)

    def stream(self, question: str):
        """Yields text chunks as Gemini generates the answer."""
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
        )
        response = self.client.models.generate_content_stream(
            model='gemini-2.5-flash',
            contents=question,
            config=config
        )
        for chunk in response:
            if chunk.text:
                yield chunk.text
