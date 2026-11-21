#!/usr/bin/env python3
"""VYGO site builder. Reads posts/*.md and writes the finished site into dist/.

Runs automatically on GitHub (see .github/workflows/pages.yml). Needs only Python 3.
"""
import html
import json
import re
import shutil
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
SITE = CFG["site_url"].rstrip("/")
DIST = ROOT / "dist"
TELEGRAM = CFG["telegram"]
INSTAGRAM = CFG["instagram"]
LOGO = f"{SITE}/assets/logo.webp"


# ---------- helpers ----------
def esc(s):
    return html.escape(str(s), quote=True)


def ld_script(objs):
    out = ""
    for o in objs:
        data = json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
        out += f'<script type="application/ld+json">{data}</script>\n'
    return out


def parse_front(text):
    text = text.replace("\r\n", "\n").lstrip("﻿")
    m = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*\n?(.*)$", text, re.S)
    meta = {}
    if not m:
        return meta, text
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip("\"'")
    return meta, m.group(2)


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "section"


def inline(s, root):
    s = html.escape(s, quote=False)

    def img(m):
        alt = m.group(1).replace('"', "&quot;")
        src = m.group(2)
        if not re.match(r"^(https?:|/|data:)", src):
            src = root + src
        return f'<img src="{src}" alt="{alt}" loading="lazy">'

    def link(m):
        url = m.group(2)
        ext = url.startswith("http")
        extra = ' target="_blank" rel="noopener"' if ext else ""
        return f'<a href="{url}"{extra}>{m.group(1)}</a>'

    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", img, s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def markdown(body, root):
    out, para = [], []
    lines = body.replace("\r\n", "\n").split("\n")
    i = 0

    def flush():
        if para:
            out.append("<p>" + inline(" ".join(para), root) + "</p>")
            para.clear()

    while i < len(lines):
        st = lines[i].strip()
        if not st:
            flush()
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", st)
        if m:
            flush()
            lvl = {1: 2, 2: 2, 3: 3, 4: 4}[len(m.group(1))]
            text = m.group(2)
            out.append(f'<h{lvl} id="{slugify(text)}">{inline(text, root)}</h{lvl}>')
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,})$", st):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if re.match(r"^[-*]\s+", st) or re.match(r"^\d+[.)]\s+", st):
            flush()
            ordered = bool(re.match(r"^\d+[.)]\s+", st))
            pat = r"^\d+[.)]\s+" if ordered else r"^[-*]\s+"
            items = []
            while i < len(lines) and re.match(pat, lines[i].strip()):
                items.append(re.sub(pat, "", lines[i].strip()))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x, root)}</li>" for x in items) + f"</{tag}>")
            continue
        if st.startswith(">"):
            flush()
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote><p>" + inline(" ".join(q), root) + "</p></blockquote>")
            continue
        if st.startswith("<"):
            flush()
            out.append(lines[i])
            i += 1
            continue
        para.append(st)
        i += 1
    flush()
    return "\n".join(out)


def video_info(url):
    if not url:
        return None
    yt = re.search(r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/|live/))([\w-]{11})", url)
    if yt:
        vid = yt.group(1)
        return {
            "kind": "youtube",
            "embed": f"https://www.youtube-nocookie.com/embed/{vid}",
            "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "watch": f"https://www.youtube.com/watch?v={vid}",
        }
    ig = re.search(r"instagram\.com/(?:[\w.]+/)?(reels?|p|tv)/([\w-]+)", url)
    if ig:
        kind = "reel" if ig.group(1).startswith("reel") else ig.group(1)
        base = f"https://www.instagram.com/{kind}/{ig.group(2)}/"
        return {"kind": "instagram", "embed": base + "embed", "thumb": None, "watch": base}
    return None


def pretty_date(d):
    return f"{d.day} {d.strftime('%b %Y')}"


# ---------- posts ----------
def load_posts():
    posts = []
    for f in sorted((ROOT / "posts").glob("*.md")):
        if f.name.startswith("_"):
            continue
        meta, body = parse_front(f.read_text(encoding="utf-8"))
        if meta.get("draft", "").lower() in ("true", "yes", "1"):
            continue
        title = meta.get("title") or f.stem.replace("-", " ").title()
        try:
            d = datetime.strptime(meta.get("date", ""), "%Y-%m-%d").date()
        except ValueError:
            d = date.today()
        text_only = re.sub(r"<[^>]+>|[#*_`>\[\]()!-]", " ", body)
        words = len(text_only.split())
        desc = meta.get("description") or " ".join(text_only.split())[:155]
        posts.append(
            {
                "slug": meta.get("slug") or f.stem,
                "title": title,
                "desc": desc,
                "date": d,
                "body": body,
                "video": video_info(meta.get("video", "")),
                "minutes": max(1, round(words / 200)),
            }
        )
    posts.sort(key=lambda p: (p["date"], p["title"]), reverse=True)
    return posts


# ---------- page pieces ----------
def header(root):
    home = root or "./"
    return f"""<header class="bar">
    <a class="mark" href="{home}">VYGO</a>
    <nav aria-label="Main">
      <a href="{home}#how">How it works</a>
      <a href="{home}#rewards">Rewards</a>
      <a href="{root}blog/">Blog</a>
      <a href="{home}#faq">FAQ</a>
    </nav>
  </header>"""


def footer(root):
    return f"""<footer>
    <span>&copy; {date.today().year} VYGO. Play Beyond Limits.</span>
    <div class="links">
      <a href="{root}blog/">Blog</a>
      <a href="{TELEGRAM}" target="_blank" rel="noopener">Telegram</a>
      <a href="{INSTAGRAM}" target="_blank" rel="noopener">Instagram</a>
    </div>
  </footer>"""


def shell(*, title, desc, path, root, body, og_type="website", image=None, ld=None):
    url = f"{SITE}/{path}"
    img = image or LOGO
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index, follow, max-image-preview:large, max-video-preview:-1">
<link rel="canonical" href="{url}">
<link rel="icon" href="{root}assets/logo.webp" type="image/webp">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="VYGO">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{img}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{img}">
<meta name="theme-color" content="#05030d">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Exo+2:ital,wght@1,700;1,800&family=Inter:wght@400;500;600&display=swap">
<link rel="stylesheet" href="{root}assets/style.css">
{ld_script(ld or [])}</head>
<body>
<div class="wrap">
  {header(root)}
{body}
  {footer(root)}
</div>
</body>
</html>
"""


def card(p, root):
    href = f"{root}blog/{p['slug']}/"
    v = p["video"]
    thumb = ""
    if v and v["thumb"]:
        thumb = f'<a class="thumb" href="{href}" tabindex="-1" aria-hidden="true"><img src="{v["thumb"]}" alt="" loading="lazy" width="480" height="360"><span class="play">Video</span></a>'
    elif v:
        thumb = f'<a class="thumb ig" href="{href}" tabindex="-1" aria-hidden="true"><span class="play">Reel</span></a>'
    return f"""<li class="post-card">
        {thumb}
        <div class="card-body">
          <p class="meta"><time datetime="{p['date'].isoformat()}">{pretty_date(p['date'])}</time> &middot; {p['minutes']} min read</p>
          <h3><a href="{href}">{esc(p['title'])}</a></h3>
          <p>{esc(p['desc'])}</p>
        </div>
      </li>"""


def cta(root):
    home = root or "./"
    return f"""<aside class="cta-box" aria-label="Join VYGO">
      <h2>Get the VYGO launch gift</h2>
      <p>Join our Telegram, follow us on Instagram and join the waitlist before the game launches.</p>
      <div class="actions">
        <a class="btn primary" href="{TELEGRAM}" target="_blank" rel="noopener">Join Telegram</a>
        <a class="btn" href="{INSTAGRAM}" target="_blank" rel="noopener">Follow on Instagram</a>
        <a class="btn" href="{home}#how">Join the Waitlist</a>
      </div>
    </aside>"""


# ---------- build ----------
def build():
    posts = load_posts()
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    shutil.copytree(ROOT / "assets", DIST / "assets")
    if (ROOT / "write").exists():
        shutil.copytree(ROOT / "write", DIST / "write")
    for extra in ("CNAME", "favicon.ico"):
        if (ROOT / extra).exists():
            shutil.copy(ROOT / extra, DIST / extra)

    # home
    latest = ""
    if posts:
        cards = "\n      ".join(card(p, "") for p in posts[:3])
        latest = f"""<section id="blog" aria-labelledby="blog-h">
      <div class="head">
        <span class="eyebrow">Blog</span>
        <h2 id="blog-h">Latest from VYGO</h2>
        <p>News, guides and videos about the game and the community.</p>
      </div>
      <ul class="post-list">
      {cards}
      </ul>
      <p class="more"><a class="btn" href="blog/">All posts</a></p>
    </section>"""
    home = (ROOT / "home.src.html").read_text(encoding="utf-8")
    home = home.replace("{{SITE_URL}}", SITE).replace("{{LATEST}}", latest)
    (DIST / "index.html").write_text(home, encoding="utf-8")

    # blog index
    (DIST / "blog").mkdir()
    root = "../"
    if posts:
        listing = '<ul class="post-list">\n      ' + "\n      ".join(card(p, root) for p in posts) + "\n    </ul>"
    else:
        listing = '<p class="empty">No posts yet. The first one is on the way.</p>'
    blog_ld = [
        {
            "@context": "https://schema.org",
            "@type": "Blog",
            "name": "VYGO Blog",
            "url": f"{SITE}/blog/",
            "publisher": {"@type": "Organization", "name": "VYGO", "logo": {"@type": "ImageObject", "url": LOGO}},
            "blogPost": [
                {"@type": "BlogPosting", "headline": p["title"], "url": f"{SITE}/blog/{p['slug']}/", "datePublished": p["date"].isoformat()}
                for p in posts
            ],
        }
    ]
    body = f"""<main>
    <div class="page-head">
      <span class="eyebrow">Blog</span>
      <h1>VYGO news and videos</h1>
      <p>Guides, updates and clips about our upcoming game, the launch gift and how to collaborate.</p>
    </div>
    {listing}
    {cta(root)}
  </main>"""
    (DIST / "blog" / "index.html").write_text(
        shell(
            title="VYGO Blog | Game News, Guides and Videos",
            desc="Read VYGO updates, guides and videos about our upcoming game, the launch gift and collaborator rewards.",
            path="blog/",
            root=root,
            body=body,
            ld=blog_ld,
        ),
        encoding="utf-8",
    )

    # posts
    for p in posts:
        root = "../../"
        v = p["video"]
        url = f"{SITE}/blog/{p['slug']}/"
        image = v["thumb"] if v and v["thumb"] else LOGO
        video_html = ""
        if v and v["kind"] == "youtube":
            video_html = f"""<div class="video-frame"><iframe src="{v['embed']}" title="{esc(p['title'])}" loading="lazy" allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe></div>
      <p class="watch"><a href="{v['watch']}" target="_blank" rel="noopener">Watch on YouTube</a></p>"""
        elif v:
            video_html = f"""<div class="video-frame ig"><iframe src="{v['embed']}" title="{esc(p['title'])}" loading="lazy" scrolling="no" allowfullscreen></iframe></div>
      <p class="watch"><a href="{v['watch']}" target="_blank" rel="noopener">Watch on Instagram</a></p>"""
        related = [x for x in posts if x is not p][:3]
        rel_html = ""
        if related:
            rel_html = f"""<section class="related" aria-labelledby="rel-h">
      <h2 id="rel-h">More from VYGO</h2>
      <ul class="post-list">
      {chr(10).join(card(x, root) for x in related)}
      </ul>
    </section>"""
        ld = [
            {
                "@context": "https://schema.org",
                "@type": "BlogPosting",
                "headline": p["title"],
                "description": p["desc"],
                "datePublished": p["date"].isoformat(),
                "dateModified": p["date"].isoformat(),
                "image": image,
                "mainEntityOfPage": url,
                "author": {"@type": "Organization", "name": "VYGO"},
                "publisher": {"@type": "Organization", "name": "VYGO", "logo": {"@type": "ImageObject", "url": LOGO}},
            },
            {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
                    {"@type": "ListItem", "position": 2, "name": "Blog", "item": f"{SITE}/blog/"},
                    {"@type": "ListItem", "position": 3, "name": p["title"], "item": url},
                ],
            },
        ]
        if v and v["kind"] == "youtube":
            ld.append(
                {
                    "@context": "https://schema.org",
                    "@type": "VideoObject",
                    "name": p["title"],
                    "description": p["desc"],
                    "thumbnailUrl": [v["thumb"]],
                    "uploadDate": p["date"].isoformat(),
                    "embedUrl": v["embed"],
                    "contentUrl": v["watch"],
                }
            )
        body = f"""<main class="article-wrap">
    <nav class="crumbs" aria-label="Breadcrumb"><a href="{root or './'}">Home</a><span aria-hidden="true">/</span><a href="{root}blog/">Blog</a><span aria-hidden="true">/</span><span>{esc(p['title'])}</span></nav>
    <article class="article">
      <header class="post-head">
        <span class="eyebrow">Blog</span>
        <h1>{esc(p['title'])}</h1>
        <p class="meta"><time datetime="{p['date'].isoformat()}">{pretty_date(p['date'])}</time> &middot; {p['minutes']} min read</p>
      </header>
      {video_html}
      <div class="prose">
{markdown(p['body'], root)}
      </div>
    </article>
    {cta(root)}
    {rel_html}
  </main>"""
        out = DIST / "blog" / p["slug"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(
            shell(
                title=f"{p['title']} | VYGO",
                desc=p["desc"],
                path=f"blog/{p['slug']}/",
                root=root,
                body=body,
                og_type="article",
                image=image,
                ld=ld,
            ),
            encoding="utf-8",
        )

    # 404
    nf = f"""<main>
    <div class="page-head">
      <span class="eyebrow">404</span>
      <h1>Page not found</h1>
      <p>That page does not exist. Go back to the <a href="{SITE}/">VYGO home page</a> or read the <a href="{SITE}/blog/">blog</a>.</p>
    </div>
  </main>"""
    (DIST / "404.html").write_text(
        shell(title="Page not found | VYGO", desc="This page does not exist.", path="404.html", root=SITE + "/", body=nf),
        encoding="utf-8",
    )

    # sitemap + robots
    urls = [(f"{SITE}/", date.today().isoformat()), (f"{SITE}/blog/", (posts[0]["date"] if posts else date.today()).isoformat())]
    urls += [(f"{SITE}/blog/{p['slug']}/", p["date"].isoformat()) for p in posts]
    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sm += "".join(f"  <url><loc>{u}</loc><lastmod>{d}</lastmod></url>\n" for u, d in urls)
    sm += "</urlset>\n"
    (DIST / "sitemap.xml").write_text(sm, encoding="utf-8")
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
    print(f"Built {len(posts)} post(s) into {DIST}")


if __name__ == "__main__":
    build()
