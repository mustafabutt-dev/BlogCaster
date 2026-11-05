"""
HTML → Markdown converter for Dev.to cross-posts.

Converts a Hugo blog article body into Dev.to-flavoured Markdown, keeping the
technical substance (prose, headings, lists, code, images, tables) and dropping
promotional sections (free license / trial blocks, "See Also" / "Read More"
link lists) and store-style links. Dev.to's content policy (Terms §11) rejects
posts that only point to an external article or exist mainly for promotion, so
the cross-post must stand on its own.
"""

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

# Headings whose whole section is promotional or just a link list → dropped
_DROP_SECTION_RE = re.compile(
    r"(free\s+(temporary\s+)?licen[cs]e|free\s+trial|get\s+a\s+licen[cs]e|"
    r"see\s+also|read\s+more|related\s+(articles|posts|resources)|useful\s+links|"
    r"explore\s+more|learn\s+more|ask\s+(a\s+)?question|get\s+help|support\s+and\s+learning|"
    r"free\s+resources|try\s+(it|for)\s+free)",
    re.I,
)

# Links to these hosts are sales/download pages: keep the anchor text, drop the link
_PROMO_HOST_RE = re.compile(r"^(purchase|products|releases|downloads?|order|buy|store|containers)\.", re.I)

# Theme wrappers inside the article body that are never content
_DROP_CLASSES = {"toc", "share-buttons", "paginav", "post-meta", "breadcrumbs", "post-tags", "anchor"}

_BLOCK_TAGS = {"p", "div", "section", "ul", "ol", "pre", "blockquote", "table", "figure",
               "h1", "h2", "h3", "h4", "h5", "h6", "details", "hr", "img", "script"}


def _clean_heading(el: Tag) -> str:
    # Hugo themes append a "#" permalink anchor to headings
    for a in el.find_all("a"):
        if a.get_text(strip=True) in ("#", "¶", "🔗") or "anchor" in (a.get("class") or []):
            a.decompose()
    return " ".join(el.get_text(" ", strip=True).split()).rstrip("#").strip()


def _escape_liquid(text: str) -> str:
    """Dev.to renders body_markdown through Liquid — raw `{{` / `{%` break or execute."""
    if "{{" in text or "{%" in text:
        return "{% raw %}\n" + text + "\n{% endraw %}"
    return text


_GIST_SRC_RE = re.compile(r"https?://gist\.github\.com/([^/?#]+)/([0-9a-f]+)(?:\.js)?(?:\?file=([^&#]+))?", re.I)

_EXT_LANG = {"java": "java", "cs": "csharp", "py": "python", "js": "javascript", "ts": "typescript",
             "php": "php", "rb": "ruby", "go": "go", "cpp": "cpp", "cc": "cpp", "c": "c", "h": "c",
             "kt": "kotlin", "swift": "swift", "vb": "vb", "sh": "bash", "ps1": "powershell",
             "xml": "xml", "json": "json", "html": "html", "css": "css", "sql": "sql", "yml": "yaml",
             "yaml": "yaml", "md": "markdown", "txt": ""}


def gist_refs(html: str) -> list[tuple[str, str, str]]:
    """List (user, gist_id, file) for every GitHub Gist embed in the article body."""
    body = find_article_body(BeautifulSoup(html, "html.parser"))
    refs = []
    for sc in (body.find_all("script") if body else []):
        m = _GIST_SRC_RE.match(sc.get("src") or "")
        if m:
            refs.append((m.group(1), m.group(2), m.group(3) or ""))
    return refs


def gist_key(user: str, gist_id: str, file: str) -> str:
    return f"{user}/{gist_id}?{file}"


class _Converter:
    def __init__(self, base_url: str, skip_image: str = "", gists: dict | None = None):
        self.base_url = base_url
        self.skip_image = skip_image
        # gist_key → list of (filename, code); pre-fetched so code is inlined, not embedded
        self.gists = gists or {}
        self.code_blocks = 0
        self.dropped_links = 0

    # ── inline ────────────────────────────────────────────────────────────
    def inline(self, node) -> str:
        if isinstance(node, NavigableString):
            return re.sub(r"\s+", " ", str(node))
        if not isinstance(node, Tag):
            return ""
        name = node.name
        if name in ("script", "style", "svg", "button", "noscript"):
            return ""
        if name == "br":
            return "  \n"
        inner = "".join(self.inline(c) for c in node.children)
        if name in ("strong", "b"):
            s = inner.strip()
            return f"**{s}**" if s else ""
        if name in ("em", "i"):
            s = inner.strip()
            return f"*{s}*" if s else ""
        if name == "code":
            s = node.get_text()
            tick = "``" if "`" in s else "`"
            return f"{tick}{s}{tick}" if s.strip() else ""
        if name == "a":
            return self.link(node, inner)
        if name == "img":
            return self.image(node)
        return inner

    def link(self, node: Tag, text: str) -> str:
        href = (node.get("href") or "").strip()
        text = text.strip()
        if not text:
            return ""
        if not href or href.startswith("#") or href.startswith("javascript:"):
            return text
        href = urljoin(self.base_url, href)
        if _PROMO_HOST_RE.match(urlparse(href).netloc):
            self.dropped_links += 1
            return text
        return f"[{text}]({href})"

    def image(self, node: Tag) -> str:
        src = node.get("src") or node.get("data-src") or ""
        if not src:
            return ""
        src = urljoin(self.base_url, src)
        if self.skip_image and src == self.skip_image:
            return ""  # already used as the Dev.to cover image
        alt = (node.get("alt") or "").replace("]", "").replace("[", "")
        return f"![{alt}]({src})"

    # ── blocks ────────────────────────────────────────────────────────────
    def code(self, el: Tag) -> str:
        code_el = el.find("code") or el
        lang = code_el.get("data-lang") or ""
        if not lang:
            for c in code_el.get("class") or []:
                if c.startswith("language-"):
                    lang = c[len("language-"):]
        text = code_el.get_text().rstrip("\n")
        if not text.strip():
            return ""
        self.code_blocks += 1
        fence = "````" if "```" in text else "```"
        return _escape_liquid(f"{fence}{lang}\n{text}\n{fence}")

    def list_block(self, el: Tag, depth: int = 0) -> str:
        ordered = el.name == "ol"
        lines = []
        n = int(el.get("start", 1) or 1)
        for li in el.find_all("li", recursive=False):
            marker = f"{n}." if ordered else "-"
            n += 1
            indent = "   " * depth
            text_parts, nested = [], []
            for child in li.children:
                if isinstance(child, Tag) and child.name in ("ul", "ol"):
                    nested.append(self.list_block(child, depth + 1))
                elif isinstance(child, Tag) and (child.name == "pre" or "highlight" in (child.get("class") or [])):
                    block = self.code(child)
                    if block:
                        nested.append("\n".join(indent + "   " + l if l else l for l in block.split("\n")))
                elif isinstance(child, Tag) and child.name == "p":
                    text_parts.append(self.inline(child).strip())
                else:
                    text_parts.append(self.inline(child))
            text = " ".join(" ".join(text_parts).split())
            if not text and not nested:
                continue
            lines.append(f"{indent}{marker} {text}")
            lines.extend(nested)
        return "\n".join(lines)

    def table(self, el: Tag) -> str:
        rows = []
        for tr in el.find_all("tr"):
            cells = [" ".join(self.inline(td).split()).replace("|", "\\|") for td in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
        out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return "\n".join(out)

    def block(self, el) -> list[str]:
        """Convert one top-level node into a list of Markdown blocks."""
        if isinstance(el, NavigableString):
            s = " ".join(str(el).split())
            return [s] if s else []
        if not isinstance(el, Tag):
            return []
        classes = set(el.get("class") or [])
        if classes & _DROP_CLASSES or el.name in ("nav", "footer", "aside", "style", "noscript", "form", "button"):
            return []
        name = el.name

        if name == "script":
            # GitHub Gist embeds carry the sample code — Dev.to has a native gist tag
            # GitHub Gist embeds carry the sample code. Inline it as fenced code —
            # Dev.to's {% gist %} tag relies on GitHub's JS embed, which rendered
            # empty in our drafts, and inline code keeps the post self-contained.
            m = _GIST_SRC_RE.match(el.get("src") or "")
            if not m:
                return []
            user, gid, file = m.group(1), m.group(2), m.group(3) or ""
            files = self.gists.get(gist_key(user, gid, file))
            if not files:
                self.code_blocks += 1  # fetch failed — fall back to Dev.to's native embed
                return [f"{{% gist https://gist.github.com/{user}/{gid} %}}"]
            out = []
            for fname, code in files:
                lang = _EXT_LANG.get(fname.rsplit(".", 1)[-1].lower(), "") if "." in fname else ""
                code = code.rstrip("\n")
                if not code.strip():
                    continue
                self.code_blocks += 1
                fence = "````" if "```" in code else "```"
                out.append(_escape_liquid(f"{fence}{lang}\n{code}\n{fence}"))
            return out
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = max(2, int(name[1]))  # the article title is the post's H1
            text = _clean_heading(el)
            return [f"{'#' * level} {text}"] if text else []
        if name == "pre" or "highlight" in classes:
            b = self.code(el)
            return [b] if b else []
        if name in ("ul", "ol"):
            links = el.find_all("a")
            if links and all((a.get("href") or "").startswith("#") for a in links):
                return []  # in-page table of contents — meaningless on Dev.to
            b = self.list_block(el)
            return [b] if b else []
        if name == "table":
            b = self.table(el)
            return [b] if b else []
        if name == "blockquote":
            inner = []
            for c in el.children:
                inner.extend(self.block(c))
            text = "\n\n".join(inner)
            return ["\n".join("> " + l if l else ">" for l in text.split("\n"))] if text.strip() else []
        if name == "hr":
            return ["---"]
        if name == "img":
            b = self.image(el)
            return [b] if b else []
        if name == "details":
            summary = el.find("summary")
            title = summary.get_text(" ", strip=True) if summary else "Details"
            if summary:
                summary.extract()
            inner = []
            for c in el.children:
                inner.extend(self.block(c))
            return [f"{{% details {title} %}}\n\n" + "\n\n".join(inner) + "\n\n{% enddetails %}"]
        if name == "figure":
            img = el.find("img")
            out = [self.image(img)] if img else []
            cap = el.find("figcaption")
            if cap and cap.get_text(strip=True):
                out.append(f"*{cap.get_text(' ', strip=True)}*")
            return [b for b in out if b]
        if name in ("div", "section", "article", "main", "header", "span") and any(
            isinstance(c, Tag) and c.name in _BLOCK_TAGS for c in el.children
        ):
            out = []
            for c in el.children:
                out.extend(self.block(c))
            return out
        text = " ".join(self.inline(el).split()) if name != "p" else self.inline(el).strip()
        text = re.sub(r"[ \t]+", " ", text).strip()
        return [text] if text else []


def _drop_promo_sections(root: Tag) -> list[str]:
    """Remove headings matching promo patterns plus everything until the next heading of same/higher level."""
    dropped = []
    for h in root.find_all(re.compile(r"^h[1-6]$")):
        if h.parent is None:
            continue
        title = _clean_heading(h)
        if not _DROP_SECTION_RE.search(title):
            continue
        level = int(h.name[1])
        dropped.append(title)
        sib = h.next_sibling
        h.decompose()
        while sib is not None:
            nxt = sib.next_sibling
            if isinstance(sib, Tag) and re.match(r"^h[1-6]$", sib.name or "") and int(sib.name[1]) <= level:
                break
            sib.extract()
            sib = nxt
    return dropped


def _tidy_punctuation(md: str) -> str:
    """Fix "**Bold** :" / "`code` ," spacing left by inline tags — outside code fences only."""
    parts = re.split(r"(^(?:```|````).*?^(?:```|````)$|\{% raw %\}.*?\{% endraw %\})", md, flags=re.S | re.M)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"(\*\*|`) ([,.:;!?])", r"\1\2", parts[i])
    return "".join(parts)


def find_article_body(soup: BeautifulSoup) -> Tag | None:
    for tag, cls in (("div", "post-content"), ("div", "entry-content"), ("div", "article-content"),
                     ("div", "content"), ("article", None), ("main", None)):
        el = soup.find(tag, class_=cls) if cls else soup.find(tag)
        if el:
            return el
    return None


def html_to_devto_markdown(html: str, base_url: str, skip_image: str = "", gists: dict | None = None) -> dict:
    """Convert an article page to Dev.to Markdown.

    Returns dict with markdown, word_count, code_blocks, dropped_sections, dropped_links.
    """
    soup = BeautifulSoup(html, "html.parser")
    body = find_article_body(soup)
    if body is None:
        return {"markdown": "", "word_count": 0, "code_blocks": 0, "dropped_sections": [], "dropped_links": 0}

    dropped = _drop_promo_sections(body)
    conv = _Converter(base_url, skip_image=skip_image, gists=gists)
    blocks = []
    for child in body.children:
        blocks.extend(conv.block(child))

    md = "\n\n".join(b.rstrip() for b in blocks if b and b.strip())
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    md = _tidy_punctuation(md)

    # Word count over prose only (code excluded) — measures substance, not code length
    prose = re.sub(r"```.*?```", " ", md, flags=re.S)
    return {
        "markdown": md,
        "word_count": len(prose.split()),
        "code_blocks": conv.code_blocks,
        "dropped_sections": dropped,
        "dropped_links": conv.dropped_links,
    }
