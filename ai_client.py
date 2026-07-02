import base64
import json
import urllib.request
import urllib.error
from google import genai
from google.genai import types

SYSTEM_PROMPT = """Your name is Shadow. You are a senior technical interviewer and assistant. 
- If specifically asked who you are or what your name is, identify yourself as Shadow.
- Otherwise, never mention your name.
- LANGUAGE RULE: Always detect the language of the user's message and reply in the EXACT same language. If they write in Hindi, reply in Hindi. If Hinglish, reply in Hinglish. If English, reply in English. Never switch languages unless the user does.
- When given an interview question:
- Give a direct, confident answer in first person.
- Use short bullet points for technical questions.
- ALWAYS wrap code snippets in standard markdown code blocks (```python, ```cpp, etc.).
- Keep explanation text under 120 words (code does not count towards this limit).
- Start answering immediately — no preamble.
"""

MAX_HISTORY = 10  # Keep last 10 exchanges to stay within token limits

FALLBACK_CHAIN = [
    {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "name": "Gemini Direct"
    },
    {
        "provider": "groq",
        "model": "qwen/qwen3.6-27b",
        "name": "Groq Qwen 3.6"
    },
    {
        "provider": "groq",
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "name": "Groq Llama 4"
    },
    {
        "provider": "openrouter",
        "model": "google/gemma-4-31b-it:free",
        "name": "OpenRouter Gemma 4"
    },
    {
        "provider": "openrouter",
        "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "name": "OpenRouter Nemotron Omni"
    },
    {
        "provider": "openrouter",
        "model": "nvidia/nemotron-nano-12b-v2-vl:free",
        "name": "OpenRouter Nemotron VL"
    },
    {
        "provider": "openrouter",
        "model": "qwen/qwen3-coder:free",
        "name": "OpenRouter Qwen 3 Coder"
    },
    {
        "provider": "openrouter",
        "model": "openai/gpt-oss-120b:free",
        "name": "OpenRouter GPT-OSS 120B"
    }
]


def stream_openai_compatible(api_key: str, base_url: str, model_id: str, messages: list):
    """Streams token chunks from an OpenAI-compatible SSE endpoint (Groq/OpenRouter)."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if "openrouter" in base_url:
        headers["HTTP-Referer"] = "https://github.com/shadowmind/app"
        headers["X-Title"] = "ShadowMind"

    data = {
        "model": model_id,
        "messages": messages,
        "stream": True
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            for line in response:
                line = line.decode('utf-8').strip()
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get('choices', [])
                        if choices:
                            delta = choices[0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                yield content
                    except Exception:
                        pass
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode('utf-8', errors='ignore')
        raise Exception(f"HTTP Error {e.code}: {error_msg}")
    except Exception as e:
        raise Exception(f"Request failed: {e}")


class GeminiClient:
    """Client wrapper that manages history and dynamically cascades down a 6-model fallback chain."""
    def __init__(self, gemini_key: str, groq_key: str = "", openrouter_key: str = ""):
        self.gemini_key = gemini_key
        self.groq_key = groq_key
        self.openrouter_key = openrouter_key
        
        self.gemini_client = None
        if gemini_key and gemini_key.strip():
            self.gemini_client = genai.Client(api_key=gemini_key)
            
        self.history = []  # List of {"role": "user"/"assistant", "content": str or list}

    def clear_history(self):
        self.history = []

    def stream(self, question: str, image_bytes: bytes = None):
        """Yields text chunks as AI generates the answer, falling back to backups if any step fails."""
        # 1. Format user message for history
        if image_bytes:
            user_content = [
                {"type": "text", "text": question},
                {"type": "image", "image_bytes": image_bytes}
            ]
        else:
            user_content = question

        # Add to history
        self.history.append({"role": "user", "content": user_content})

        # Trim history
        if len(self.history) > MAX_HISTORY * 2:
            self.history = self.history[-(MAX_HISTORY * 2):]

        last_error = None
        fallback_active = False

        for candidate in FALLBACK_CHAIN:
            provider = candidate["provider"]
            model_id = candidate["model"]
            friendly_name = candidate["name"]
            
            # Fetch relevant key
            key = None
            if provider == "gemini":
                key = self.gemini_key
            elif provider == "groq":
                key = self.groq_key
            elif provider == "openrouter":
                key = self.openrouter_key
                
            if not key or not key.strip():
                # Skip if key is not configured
                continue
                
            if fallback_active:
                yield f"\n\n⚠️ **[Rotating to {friendly_name}...]**\n\n"
                
            try:
                full_answer = []
                if provider == "gemini":
                    # Initialize client lazily if needed
                    if not self.gemini_client:
                        self.gemini_client = genai.Client(api_key=key)
                    
                    config = types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                    )
                    
                    # Convert agnostic history to Gemini content parts
                    gemini_contents = []
                    for msg in self.history:
                        gemini_role = "model" if msg["role"] == "assistant" else "user"
                        parts = []
                        content = msg["content"]
                        if isinstance(content, str):
                            parts.append(types.Part.from_text(text=content))
                        elif isinstance(content, list):
                            for item in content:
                                if item.get("type") == "text":
                                    parts.append(types.Part.from_text(text=item["text"]))
                                elif item.get("type") == "image":
                                    parts.append(types.Part.from_bytes(data=item["image_bytes"], mime_type='image/png'))
                                    
                        gemini_contents.append(types.Content(role=gemini_role, parts=parts))
                        
                    response = self.gemini_client.models.generate_content_stream(
                        model=model_id,
                        contents=gemini_contents,
                        config=config
                    )
                    for chunk in response:
                        if chunk.text:
                            full_answer.append(chunk.text)
                            yield chunk.text
                            
                elif provider in ("groq", "openrouter"):
                    base_url = "https://api.groq.com/openai/v1" if provider == "groq" else "https://openrouter.ai/api/v1"
                    
                    # Convert agnostic history to OpenAI message objects
                    openai_messages = []
                    for msg in self.history:
                        role = "assistant" if msg["role"] == "assistant" else "user"
                        content = msg["content"]
                        if isinstance(content, str):
                            openai_messages.append({"role": role, "content": content})
                        elif isinstance(content, list):
                            formatted_content = []
                            for item in content:
                                if item.get("type") == "text":
                                    formatted_content.append({"type": "text", "text": item["text"]})
                                elif item.get("type") == "image":
                                    b64_str = base64.b64encode(item["image_bytes"]).decode('utf-8')
                                    formatted_content.append({
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{b64_str}"
                                        }
                                    })
                            openai_messages.append({"role": role, "content": formatted_content})
                            
                    openai_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + openai_messages
                    
                    for chunk in stream_openai_compatible(
                        api_key=key,
                        base_url=base_url,
                        model_id=model_id,
                        messages=openai_messages
                    ):
                        full_answer.append(chunk)
                        yield chunk
                
                # If generation was successful, commit assistant response and exit rotation
                if full_answer:
                    self.history.append({
                        "role": "assistant",
                        "content": "".join(full_answer)
                    })
                    return
                    
            except Exception as e:
                last_error = e
                fallback_active = True
                print(f"[Fallback] {friendly_name} failed: {e}")
                continue
                
        # If all options failed, raise final error
        if last_error:
            raise last_error
        else:
            raise Exception("No active API keys configured or all providers failed.")
