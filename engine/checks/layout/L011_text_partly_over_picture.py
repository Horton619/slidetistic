from engine.core import Check, Finding, Status
from engine.core.layout.pdf import EMU_PER_PT
from engine.core import fit


class TextPartlyOverPicture(Check):
    id = "L011"
    title = "Text partly over a picture"
    group = "layout"
    description = "Text that sits half on, half off a picture. Fully on a picture is assumed intentional (titles on photos)."
    report_only = True
    requires = ["layout"]
    sources = ["any"]
    thresholds = ["overlap_min_pt"]

    def detect(self, deck, ctx):
        if ctx.layout is None:
            return []
        tol = self.threshold(ctx, "overlap_min_pt") * EMU_PER_PT
        shapes = deck.iter_shapes()
        names = {(sv.slide_number, sv.shape_id): sv.name for sv in shapes}
        findings = []
        for n in range(1, len(deck.slides) + 1):
            pics = [sv for sv in shapes if sv.slide_number == n and fit.is_graphic(sv)]
            for sid, st in ctx.layout.slide(n).items():
                if not st.bounds:
                    continue
                l, t, r, b = st.bounds
                for p in pics:
                    pb = p.bounds
                    w = min(r, pb.right) - max(l, pb.left)
                    h = min(b, pb.bottom) - max(t, pb.top)
                    inside = l >= pb.left - tol and r <= pb.right + tol and t >= pb.top - tol and b <= pb.bottom + tol
                    if w > tol and h > tol and not inside:
                        share = w * h / ((r - l) * (b - t)) if (r - l) * (b - t) else 0
                        findings.append(Finding(self.id, Status.YELLOW,
                            f"Text is partly over picture '{p.name}' ({share:.0%} of the text area). Check it's readable.",
                            slide=n, shape_id=sid, shape_name=names.get((n, sid)), subject=f"over {p.shape_id}",
                            evidence={"picture": p.name, "share": round(share, 2), "box_emu": [l, t, r, b],
                                      "rule": "drawn text area intersects the picture but isn't fully inside it "
                                              "(fully inside = assumed intentional)"}))
        return findings
