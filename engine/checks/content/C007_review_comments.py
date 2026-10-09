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
        findings = []
        for n, slide in enumerate(deck.slides, 1):
            count = sum(1 for rel in slide.part.rels.values()
                        if not rel.is_external and rel.target_part.content_type in COMMENT_TYPES)
            if count:
                findings.append(Finding(self.id, Status.YELLOW,
                    "Slide has review comments. Check the deck is the final version.",
                    slide=n, subject="comments", evidence={"comment_parts": count}))
        return findings
