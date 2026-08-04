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
        "name": "Gemini Direct",
        "supports_vision": True
    },
    {
        "provider": "groq",
        "model": "llama-3.2-90b-vision-preview",
        "name": "Groq Llama 3.2 90B Vision",
        "supports_vision": True
    },
    {
        "provider": "groq",
        "model": "llama-3.2-11b-vision-preview",
        "name": "Groq Llama 3.2 11B Vision",
        "supports_vision": True
    },
    {
        "provider": "openrouter",
        "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "name": "OpenRouter Nemotron Omni",
        "supports_vision": True
    },
    {
        "provider": "openrouter",
        "model": "nvidia/nemotron-nano-12b-v2-vl:free",
        "name": "OpenRouter Nemotron VL",
        "supports_vision": True
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
    """Client wrapper that manages history and dynamically cascades down a multi-key fallback chain."""
    def __init__(self, gemini_key=None, groq_key: str = "", openrouter_key: str = ""):
        if isinstance(gemini_key, list):
            self.gemini_keys = [k.strip() for k in gemini_key if isinstance(k, str) and k.strip()]
        elif isinstance(gemini_key, str) and gemini_key.strip():
            self.gemini_keys = [gemini_key.strip()]
        else:
            self.gemini_keys = []
            
        self.groq_key = groq_key
        self.openrouter_key = openrouter_key
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
            
        # Check if the conversation contains any images
        has_images = False
        for msg in self.history:
            if isinstance(msg["content"], list):
                for item in msg["content"]:
                    if item.get("type") == "image":
                        has_images = True
                        break
            if has_images:
                break

        # Build dynamic effective fallback chain (including all provided Gemini keys)
        effective_chain = []
        for idx, g_key in enumerate(self.gemini_keys):
            name = f"Gemini Key #{idx+1}" if len(self.gemini_keys) > 1 else "Gemini Direct"
            effective_chain.append({
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "name": name,
                "key": g_key,
                "supports_vision": True
            })

        for candidate in FALLBACK_CHAIN:
            if candidate["provider"] == "gemini":
                continue
            cand_copy = dict(candidate)
            if candidate["provider"] == "groq":
                cand_copy["key"] = self.groq_key
            elif candidate["provider"] == "openrouter":
                cand_copy["key"] = self.openrouter_key
            effective_chain.append(cand_copy)

        last_error = None
        fallback_active = False

        for candidate in effective_chain:
            provider = candidate["provider"]
            model_id = candidate["model"]
            friendly_name = candidate["name"]
            supports_vision = candidate.get("supports_vision", False)
            key = candidate.get("key", "")
            
            # Skip text-only models if we have images in history
            if has_images and not supports_vision:
                continue
                
            if not key or not key.strip():
                # Skip if key is not configured
                continue
                
            if fallback_active:
                yield f"\n\n⚠️ **[Rotating to {friendly_name}...]**\n\n"
                
            try:
                full_answer = []
                if provider == "gemini":
                    gemini_client = genai.Client(api_key=key)
                    
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
                        
                    response = gemini_client.models.generate_content_stream(
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
