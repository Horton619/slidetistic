from engine.core import Check, Finding, Status

COMMENT_TYPES = (
    "application/vnd.openxmlformats-officedocument.presentationml.comments+xml",   # classic
    "application/vnd.ms-powerpoint.comments+xml",                                  # modern (threaded)
)


class ReviewComments(Check):
    id = "C007"
    title = "Review comments left in"
    group = "content"
    description = "Comment threads still in the deck. Harmless in the show, but a sign the deck may not be final."
    # Fix (remove comments) waits for a real PowerPoint-saved fixture: modern comments may also be
    # referenced from extension XML we haven't seen. See CLAUDE.md "Never guess PowerPoint XML".
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        # One finding per deck (Dropbox corpus: 101 per-slide findings in 32 decks was noise).
        slides = [n for n, slide in enumerate(deck.slides, 1)
                  if any(not rel.is_external and rel.target_part.content_type in COMMENT_TYPES
                         for rel in slide.part.rels.values())]
        if not slides:
            return []
        return [Finding(self.id, Status.YELLOW,
                        f"Review comments on {len(slides)} slide{'s' * (len(slides) != 1)} ({_ranges(slides)}). "
                        f"Check this is the final version.", subject="comments", evidence={"slides": slides})]


def _ranges(nums) -> str:
    out, start = [], None
    for i, n in enumerate(nums):
        start = n if start is None else start
        if i + 1 == len(nums) or nums[i + 1] != n + 1:
            out.append(str(start) if start == n else f"{start}–{n}")
            start = None
    return ", ".join(out)
