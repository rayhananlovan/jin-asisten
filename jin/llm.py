from __future__ import annotations

import json
import urllib.error
import urllib.request

from jin.actions import TOOLS, describe_call, execute, match_intents
from jin.config import OLLAMA_MODEL, OLLAMA_URL
from jin import memory as jin_memory
from jin.magic import current_form
from jin.persona import SYSTEM_PROMPT
from jin import smart

INSTALL_HINT = (
    "Jin tidak pakai API berbayar. Otaknya lewat Ollama di laptop.\n\n"
    "1. Install Ollama: https://ollama.com/download\n"
    "2. Buka Command Prompt, jalankan:\n"
    f"   ollama pull {OLLAMA_MODEL}\n"
    "3. Pastikan Ollama sudah jalan (ikon di taskbar), lalu buka Jin lagi."
)


def _chat(messages: list[dict], use_tools: bool = False, on_token=None) -> dict:
    payload = {
        "model": OLLAMA_MODEL,
        "stream": True,
        "messages": messages,
        "options": {"temperature": 0.4},
    }
    if use_tools:
        payload["tools"] = TOOLS
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    content: list[str] = []
    tool_calls: list[dict] = []
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            for line in response:
                if not line.strip():
                    continue
                chunk = json.loads(line.decode("utf-8"))
                if chunk.get("error"):
                    raise RuntimeError(
                        f"Ollama error: {chunk['error']}\n\nCoba jalankan: ollama pull {OLLAMA_MODEL}"
                    )
                message = chunk.get("message") or {}
                piece = message.get("content") or ""
                if piece:
                    content.append(piece)
                    if on_token:
                        on_token("".join(content))
                tool_calls.extend(message.get("tool_calls") or [])
                if chunk.get("done"):
                    break
    except urllib.error.URLError as exc:
        raise RuntimeError(INSTALL_HINT) from exc
    result: dict = {"role": "assistant", "content": "".join(content)}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


def _arguments(call: dict) -> dict:
    raw = (call.get("function") or {}).get("arguments") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _with_tools(messages: list[dict], on_tool=None, on_token=None) -> str:
    current = list(messages)
    for _ in range(6):
        message = _chat(current, use_tools=True, on_token=on_token)
        tool_calls = message.get("tool_calls") or []
        text = (message.get("content") or "").strip()
        if not tool_calls:
            return text
        current.append(message)
        for call in tool_calls:
            name = (call.get("function") or {}).get("name") or ""
            args = _arguments(call)
            if on_tool:
                on_tool(name, args)
            result = execute(name, args)
            current.append({"role": "tool", "content": result})
    return text or "Aksi sudah dijalankan."


def reply(history: list[dict[str, str]], on_tool=None, on_token=None) -> str:
    """on_token receives the full text-so-far each time a new piece streams in."""
    history = [dict(item) for item in history]
    last_index = next(
        (index for index in range(len(history) - 1, -1, -1) if history[index].get("role") == "user"),
        None,
    )
    last_user = history[last_index]["content"] if last_index is not None else ""
    resolved = smart.resolve_references(last_user) if last_user else ""
    if last_index is not None and resolved:
        history[last_index]["content"] = resolved
    if last_user:
        smart.absorb_facts(resolved or last_user)

    form = current_form()
    extra = [SYSTEM_PROMPT, f"Wujud aktif sekarang: {form}."]
    recalled = jin_memory.recall_prompt(resolved or last_user)
    if recalled:
        extra.append(recalled)
    ambient = smart.context_prompt()
    if ambient:
        extra.append(ambient)
    if resolved and last_user and resolved != last_user:
        extra.append(f"Bos Rehan bilang: '{last_user}'. Yang dimaksud: '{resolved}'.")
    if recalled:
        extra.append(
            "Kalau bos bertanya soal proyek/kejadian/fakta lama, "
            "jawab dari blok 'Ingatan relevan' di atas. Jangan bilang tidak ingat "
            "kalau ada yang cocok di situ."
        )

    messages: list[dict] = [{"role": "system", "content": "\n\n".join(extra)}, *history]
    if last_user:
        intents = match_intents(resolved or last_user)
    else:
        intents = []
    if intents:
        results = []
        for name, args in intents:
            if on_tool:
                on_tool(name, args)
            results.append(f"{describe_call(name, args)}\n{execute(name, args)}")
        joined = "\n\n".join(results)
        messages.append(
            {
                "role": "system",
                "content": (
                    "Beberapa aksi laptop sudah dijalankan:\n"
                    f"{joined}\n"
                    "Sampaikan ke bos Rehan singkat dan jelas. Jangan bilang kamu tidak bisa."
                ),
            }
        )
        message = _chat(messages, use_tools=False, on_token=on_token)
        return (message.get("content") or joined).strip()
    return (
        _with_tools(messages, on_tool=on_tool, on_token=on_token).strip()
        or "Aku belum bisa menjawab itu, bos Rehan."
    )
