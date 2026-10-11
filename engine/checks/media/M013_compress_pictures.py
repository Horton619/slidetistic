from engine.core import Check, Finding, FixRefused, Status
from engine.core import compress


class CompressPictures(Check):
    id = "M013"
    title = "Pictures larger than the screen needs"
    group = "media"
    description = ("Full-resolution photos far beyond what a 1080p screen shows. Compressing them (like PowerPoint's "
                   "150 ppi with cropped areas deleted) makes the file smaller and the deck snappier.")
    default_fix = False          # the operator turns it on per deck (David 2026-10-11)
    sources = ["any"]
    thresholds = ["compress_target_width_px", "compress_jpeg_quality", "compress_pitch_min_pct", "compress_pitch_min_mb"]

    def detect(self, deck, ctx):
        plans = compress.plans(deck, int(self.threshold(ctx, "compress_target_width_px")))
        deck_bytes = deck.path.stat().st_size
        saved = sum(p.bytes - p.estimate for p in plans if p.estimate < p.bytes)
        pct = 100 * saved / deck_bytes if deck_bytes else 0
        if pct < self.threshold(ctx, "compress_pitch_min_pct") or saved / 1e6 < self.threshold(ctx, "compress_pitch_min_mb"):
            return []
        before, after = deck_bytes / 1e6, (deck_bytes - saved) / 1e6
        return [Finding(self.id, Status.YELLOW,
            f"Compressing {len(plans)} pictures for a 1080p screen would shrink this deck from {before:.0f} MB "
            f"to about {after:.0f} MB (−{pct:.0f}%). Turn on Compress pictures to do it on repair.",
            subject="compress",
            evidence={"deck_mb": round(before, 1), "estimate_mb": round(after, 1), "saving_pct": round(pct),
                      "pictures": len(plans), "cropped": sum(1 for p in plans if p.crop),
                      "rule": f"each picture resized to what it fills on a {int(self.threshold(ctx, 'compress_target_width_px'))} px "
                              f"wide slide (PowerPoint's 150 ppi), cropped areas deleted when every use crops alike; "
                              f"estimate from pixel area; suggested at ≥{self.threshold(ctx, 'compress_pitch_min_pct')}% "
                              f"and ≥{self.threshold(ctx, 'compress_pitch_min_mb')} MB"})]

    def fix(self, deck, finding, edits, ctx):
        quality = int(self.threshold(ctx, "compress_jpeg_quality"))
        done = 0
        for plan in compress.plans(deck, int(self.threshold(ctx, "compress_target_width_px"))):
            data = compress.encode(plan, quality)
            if data is None:
                continue
            (w, h), (nw, nh) = plan.size, plan.new_size
            edits.replace_blob(plan.part, data, prop="picture",
                               before=f"{w}×{h} px, {plan.bytes / 1e6:.1f} MB",
                               after=f"{nw}×{nh} px, {len(data) / 1e6:.1f} MB" + (", cropped area deleted" if plan.crop else ""))
            if plan.crop:       # the pixels now ARE the visible part: drop the crop so nothing shifts
                for u in plan.uses:
                    edits.replace_element(u.slide_part, u.src_rect, None, prop="crop",
                                          before="cropped in PowerPoint", after="cropped area deleted")
            done += 1
        if not done:
            raise FixRefused("no picture got meaningfully smaller")
