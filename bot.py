# -*- coding: utf-8 -*-
"""
Telegram-бот «ТехноВести»: берёт свежие новости из российских источников
о компьютерных технологиях, физических открытиях и космосе
(Habr, 3DNews, Hi-News, CNews, N+1, Naked Science), формирует краткий
пост с картинкой и публикует в Telegram-канал.

Режимы:
  python bot.py            — опубликовать один пост
  python bot.py --digest   — опубликовать дайджест из 3–4 главных новостей
  python bot.py --test [--digest] — показать пост, НЕ отправлять

Настройки: config.json рядом со скриптом (bot_token, chat_id, max_chars)
или переменные окружения BOT_TOKEN и CHAT_ID (приоритет выше — для
GitHub Actions Secrets).
"""
import json, os, re, sys, html
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")
POSTED_PATH = os.path.join(BASE, "posted.json")

FEEDS = [
    ("Habr", "https://habr.com/ru/rss/news/"),
    ("3DNews", "https://3dnews.ru/news/rss/"),
    ("Hi-News", "https://hi-news.ru/feed"),
    ("CNews", "https://www.cnews.ru/inc/rss/news.xml"),
    ("N+1", "https://nplus1.ru/rss"),
    ("Naked Science", "https://naked-science.ru/?feed=rss2"),
]

MEDIA_NS = "http://search.yahoo.com/mrss/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
IMG_RE = re.compile(r'<img[^>]+src=["\'](http[^"\']+)["\']', re.I)


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def image_from_element(el, raw_html):
    """Картинка из RSS/Atom-элемента: media:content, enclosure, <img> в тексте."""
    for tag in (f"{{{MEDIA_NS}}}content", f"{{{MEDIA_NS}}}thumbnail"):
        for m in el.iter(tag):
            u = m.get("url")
            if u and (m.get("medium") in (None, "image") or "image" in (m.get("type") or "")) \
                    or u and re.search(r"\.(jpe?g|png|webp)(\?|$)", u, re.I):
                return u
    for enc in el.iter("enclosure"):
        if "image" in (enc.get("type") or "") and enc.get("url"):
            return enc.get("url")
    m = IMG_RE.search(raw_html or "")
    if m:
        return m.group(1)
    return None


def image_from_page(url):
    """Запасной вариант: og:image со страницы статьи."""
    try:
        html_text = http_get(url, timeout=15).decode("utf-8", "ignore")
        m = re.search(r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                      html_text, re.I) or \
            re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']',
                      html_text, re.I)
        if m:
            return m.group(1)
    except Exception as e:
        print(f"[warn] og:image: {e}", file=sys.stderr)
    return None


def fetch_items():
    items = []
    for name, url in FEEDS:
        try:
            data = http_get(url)
            root = ET.fromstring(data)
        except Exception as e:
            print(f"[warn] {name}: {e}", file=sys.stderr)
            continue
        # RSS 2.0
        for it in root.iter("item"):
            t = it.findtext("title")
            l = it.findtext("link")
            d_raw = it.findtext("description") or it.findtext("summary") or ""
            if t and l:
                items.append((name, t.strip(), l.strip(), strip_tags(d_raw),
                              image_from_element(it, d_raw)))
        # Atom
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for it in root.iter("{http://www.w3.org/2005/Atom}entry"):
            t = it.findtext("a:title", namespaces=ns)
            link_el = it.find("a:link", namespaces=ns)
            d_raw = it.findtext("a:summary", namespaces=ns) or it.findtext("a:content", namespaces=ns) or ""
            if t is not None and link_el is not None:
                items.append((name, t.strip(), link_el.get("href", ""), strip_tags(d_raw),
                              image_from_element(it, d_raw)))
    return items


def summarize(text, max_chars):
    """Краткий пост: первые 2-3 предложения в пределах лимита."""
    sents = re.split(r"(?<=[.!?…])\s+", text)
    out = ""
    for s in sents:
        cand = (out + " " + s).strip()
        if len(cand) > max_chars:
            break
        out = cand
        if out.count(".") + out.count("!") + out.count("?") >= 3:
            break
    if not out:
        out = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return out


def load_posted():
    if os.path.exists(POSTED_PATH):
        try:
            return set(json.load(open(POSTED_PATH, encoding="utf-8")))
        except Exception:
            pass
    return set()


def save_posted(posted):
    json.dump(sorted(posted)[-2000:], open(POSTED_PATH, "w", encoding="utf-8"))


def telegram_api(token, method, params):
    url = f"https://api.telegram.org/bot{token}/{method}"
    payload = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=payload, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def send_post(token, chat_id, caption, image_url):
    """Пост с картинкой (sendPhoto); если картинка недоступна — обычный текст."""
    if image_url:
        try:
            resp = telegram_api(token, "sendPhoto", {
                "chat_id": chat_id, "photo": image_url,
                "caption": caption, "parse_mode": "HTML"})
            if resp.get("ok"):
                return resp
            print(f"[warn] sendPhoto: {resp}", file=sys.stderr)
        except Exception as e:
            print(f"[warn] sendPhoto: {e}", file=sys.stderr)
    return telegram_api(token, "sendMessage", {
        "chat_id": chat_id, "text": caption,
        "parse_mode": "HTML", "disable_web_page_preview": "false"})


def make_digest_post(fresh, n=4):
    """Дайджест из n главных новостей разных источников.
    Возвращает (текст, картинка, использованные ссылки)."""
    NUMS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    seen, picked = set(), []
    for it in fresh:  # первый проход: по одной новости с источника
        if it[0] not in seen:
            picked.append(it)
            seen.add(it[0])
        if len(picked) >= n:
            break
    for it in fresh:  # добор, если источников меньше n
        if len(picked) >= n:
            break
        if it not in picked:
            picked.append(it)
    lines, image = [], None
    for i, (source, title, link, desc, img) in enumerate(picked[:n]):
        lines.append(f"{NUMS[i]} <b>{html.escape(title)}</b>\n"
                     f"<a href=\"{link}\">{source}</a>")
        if not image and img:
            image = html.unescape(img)
    if not lines:
        return None, None, []
    post = "🌅 <b>Главное за сутки: IT, наука и космос</b>\n\n" + "\n\n".join(lines)
    post += "\n\n#дайджест #IT #наука #космос"
    return post, image, [it[2] for it in picked[:n]]


def main():
    test_mode = "--test" in sys.argv
    digest_mode = "--digest" in sys.argv

    cfg = {}
    if os.path.exists(CONFIG_PATH):
        cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))
    max_chars = int(cfg.get("max_chars", 700))
    token = os.environ.get("BOT_TOKEN") or cfg.get("bot_token", "")
    chat_id = os.environ.get("CHAT_ID") or cfg.get("chat_id", "")

    posted = load_posted()
    items = fetch_items()
    fresh = [it for it in items if it[2] and it[2] not in posted]
    if not fresh:
        print("Свежих новостей нет — все уже опубликованы.")
        return

    if digest_mode:
        post, image, used_links = make_digest_post(fresh)
        if not post:
            print("Не удалось собрать дайджест.")
            return
    else:
        source, title, link, desc, image = fresh[0]
        if not image:
            image = image_from_page(link)
        if image:
            image = html.unescape(image)
        desc_short = summarize(desc, max_chars) if desc else ""
        post = f"💡 <b>{html.escape(title)}</b>\n\n"
        if desc_short:
            post += html.escape(desc_short) + "\n\n"
        post += f"Источник: {source} — <a href=\"{link}\">читать полностью</a>\n#IT #наука #космос"
        used_links = [link]

    if test_mode:
        print("Картинка:", image or "(не найдена)")
        print("=" * 60)
        print(re.sub(r"<[^>]+>", "", post))
        print("=" * 60)
        return

    if not token or "ВСТАВЬТЕ" in token:
        print("ОШИБКА: не задан bot_token (config.json или BOT_TOKEN)", file=sys.stderr)
        sys.exit(1)

    resp = send_post(token, chat_id, post, image)
    if resp.get("ok"):
        posted.update(used_links)
        save_posted(posted)
        print("Опубликовано.")
    else:
        print("Ошибка Telegram API:", resp, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
