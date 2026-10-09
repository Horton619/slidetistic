from engine.core import Check, Finding, Status
from engine.core import content


class LinkLeavesShow(Check):
    id = "P004"
    title = "Link leaves the show"
    group = "playback"
    description = "Clickable links to web pages or files. One stray click opens a browser in front of the audience."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        # One finding per slide: reference slides often carry a dozen citation links.
        by_slide: dict[int, list] = {}
        for link in content.hyperlinks(deck):
            # Media links are M005/M006's; local paths are X004's.
            if content.media_kind(link.url) or content.is_local_path(link.url):
                continue
            by_slide.setdefault(link.slide, []).append(link)
        findings = []
        for n, links in sorted(by_slide.items()):
            urls = list(dict.fromkeys(l.url for l in links))
            what = urls[0] if len(urls) == 1 else f"{len(urls)} web pages ({urls[0]}, …)"
            findings.append(Finding(self.id, Status.YELLOW,
                f"Clickable link{'s' * (len(urls) > 1)} on this slide open{'s' * (len(urls) == 1)} {what} outside the show.",
                slide=n, subject="links", evidence={"urls": urls}))
        return findings
