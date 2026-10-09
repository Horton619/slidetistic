from engine.core import Check, Finding, Status
from engine.core import content


class MediaLinksToDownload(Check):
    id = "M006"
    title = "Media links to download"
    group = "media"
    description = "Video and file-share links in slide text, speaker notes or hyperlinks. Listed so they can be fetched and embedded."
    report_only = True
    sources = ["google", "canva", "keynote", "any"]
    runs_after = ["M005"]

    def detect(self, deck, ctx):
        names = {n: content.slide_name(s, n) for n, s in enumerate(deck.slides, 1)}
        # Pictures linking to video sites are M005's; everything else media-like is listed here.
        links = content.text_urls(deck) + [l for l in content.hyperlinks(deck)
                                           if not (l.where == "picture link" and content.is_video_site(l.url))]
        findings, seen = [], set()
        for link in links:
            kind = content.media_kind(link.url)
            if not kind or (link.slide, link.url) in seen:
                continue
            seen.add((link.slide, link.url))
            findings.append(Finding(self.id, Status.YELLOW,
                f"{kind} link in {link.where}: download it if it's meant to play in the show.",
                slide=link.slide, shape_id=link.shape_id, shape_name=link.shape_name, subject=link.url,
                evidence={"url": link.url, "site": kind, "found_in": link.where, "slide_name": names[link.slide]}))
        return findings
