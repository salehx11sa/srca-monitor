"""التصنيف بالذكاء الاصطناعي المجاني: Gemini أولًا، ثم Groq، ثم القواعد. لا Claude."""
import json, re
from pathlib import Path

from .. import config
from ..util import post, log
from . import rules

GUIDE = (Path(__file__).parent / "guide_ar.md").read_text(encoding="utf-8")
FIELDS = ("relevance", "priority", "sentiment", "ctype", "summary", "reason", "region")
OK_REL = {"مؤكد", "محتمل", "مستبعد"}
OK_PRI = {"عاجل", "مهم", "اعتيادي", ""}


class AIDown(Exception):
    pass


def _prompt(batch, examples):
    lines = []
    for i, it in enumerate(batch):
        extra = it.get("extra") or {}
        ctx = []
        if extra.get("reply_to"):
            ctx.append(f"رد على @{extra['reply_to']}")
        if it.get("quoted"):
            ctx.append("يقتبس: " + it["quoted"][:300])
        if it.get("location"):
            ctx.append("موقع الحساب: " + it["location"][:40])
        lines.append(f"[{i}] منصة={it['platform']} | الحساب=@{it.get('author', '')} ({it.get('author_name', '')[:30]}) | "
                     f"{' | '.join(ctx)}\nالنص: {it.get('text', '')[:1200]}")
    ex = ""
    if examples:
        ex = "\n\nتصحيحات سابقة من صاحب الرصد (اتبعها):\n" + "\n".join(
            f"- «{e['text'][:160]}» ← {e['verdict']}" for e in examples[:25])
    return (GUIDE + ex + "\n\nصنّف المنشورات التالية. أرجع JSON فقط بالشكل: "
            '{"results":[{"i":0,"relevance":"مؤكد|محتمل|مستبعد","priority":"عاجل|مهم|اعتيادي","sentiment":"...",'
            '"ctype":"...","summary":"...","reason":"...","region":""}]} — عنصر لكل منشور بنفس الرقم i. '
            'للمستبعد اترك priority فارغة.\n\n' + "\n\n".join(lines))


def _parse(txt, n):
    txt = txt.strip()
    m = re.search(r"\{.*\}|\[.*\]", txt, re.S)
    data = json.loads(m.group(0) if m else txt)
    if isinstance(data, dict):
        data = data.get("results") or data.get("items") or []
    out = {}
    for r in data:
        try:
            i = int(r.get("i"))
        except Exception:
            continue
        if 0 <= i < n and r.get("relevance") in OK_REL:
            r["priority"] = r.get("priority", "") if r.get("priority", "") in OK_PRI else "اعتيادي"
            out[i] = {k: str(r.get(k, "") or "")[:400] for k in FIELDS}
    if len(out) < n:
        raise ValueError(f"incomplete {len(out)}/{n}")
    return out


def _gemini(prompt, n):
    if not config.GEMINI_KEY:
        raise AIDown("NO_GEMINI_KEY")
    last = None
    for model in config.GEMINI_MODELS:
        try:
            r = post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                     headers={"x-goog-api-key": config.GEMINI_KEY}, retries=2, timeout=90,
                     json={"contents": [{"parts": [{"text": prompt}]}],
                           "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}})
            if r.status_code != 200:
                last = f"{model}:HTTP{r.status_code}"
                continue
            parts = r.json()["candidates"][0]["content"]["parts"]
            return _parse("".join(p.get("text", "") for p in parts), n), "gemini:" + model
        except Exception as e:
            last = f"{model}:{e}"
    raise AIDown(str(last))


def _groq(prompt, n):
    if not config.GROQ_KEY:
        raise AIDown("NO_GROQ_KEY")
    last = None
    for model in config.GROQ_MODELS:
        try:
            r = post("https://api.groq.com/openai/v1/chat/completions", retries=1, timeout=90,
                     headers={"Authorization": f"Bearer {config.GROQ_KEY}"},
                     json={"model": model, "temperature": 0.1, "response_format": {"type": "json_object"},
                           "messages": [{"role": "user", "content": prompt}]})
            if r.status_code != 200:
                last = f"{model}:HTTP{r.status_code}"
                continue
            return _parse(r.json()["choices"][0]["message"]["content"], n), "groq:" + model
        except Exception as e:
            last = f"{model}:{e}"
    raise AIDown(str(last))


def classify(items, examples=(), batch_size=12):
    """يرجع (نتائج لكل عنصر بنفس الترتيب، الطبقة المستخدمة)."""
    results, used = [], set()
    for k in range(0, len(items), batch_size):
        batch = items[k:k + batch_size]
        prompt = _prompt(batch, list(examples))
        got = None
        for fn in (_gemini, _groq):
            try:
                got, who = fn(prompt, len(batch))
                for v in got.values():
                    v["classifier"] = who
                used.add(fn.__name__.strip("_"))
                break
            except Exception as e:
                log.warning("التصنيف %s تعذر: %s", fn.__name__, str(e)[:120])
        if got is None:
            used.add("rules")
            results += [rules.classify(it) for it in batch]
        else:
            results += [got[i] for i in range(len(batch))]
    return results, used
