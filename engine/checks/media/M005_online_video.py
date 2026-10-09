from engine.core import Check, Finding, Status
from engine.core import content


class OnlineVideo(Check):
    id = "M005"
    title = "Online video"
    group = "media"
    description = "Video that plays from the web (YouTube, Vimeo…). Needs venue internet; download and embed it instead."
    report_only = True
    sources = ["google", "canva", "keynote", "any"]

    def detect(self, deck, ctx):
        names = {n: content.slide_name(s, n) for n, s in enumerate(deck.slides, 1)}
        found: dict[tuple, Finding] = {}
        for link in content.hyperlinks(deck):
            if link.where == "picture link" and content.is_video_site(link.url):
                self._add(found, link.slide, link.shape_id, link.shape_name, link.url,
                          "a picture that opens the video in a browser", names)
        for rel in content.external_rels(deck):
            if rel.slide and content.is_video_site(rel.target) and not rel.reltype.endswith("/hyperlink"):
                self._add(found, rel.slide, None, None, rel.target, "a video player that streams it", names)
        return list(found.values())

    def _add(self, found, slide, shape_id, shape_name, url, how, names):
        key = (slide, url)
        if key in found:
            return
        found[key] = Finding(self.id, Status.RED,
            f"Online video ({content.media_kind(url)}) shown as {how}. It needs venue internet. "
            f"Download it and embed the file.",
            slide=slide, shape_id=shape_id, shape_name=shape_name, subject=url,
            evidence={"url": url, "site": content.media_kind(url), "slide_name": names[slide]})
