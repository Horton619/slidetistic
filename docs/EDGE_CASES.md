# Edge cases log

One entry per "oh by the way". Newest first.

| Date | What was seen | Source | Check | Fixture | Status |
| --- | --- | --- | --- | --- | --- |
| 2026-10-07 | Real font names that end in a style word ('Arial Rounded MT Bold') must not be stripped | Design | F001 | `test_f001_real_family_ending_in_bold_is_left_alone` | Yellow, no fix unless the base family is known |
| 2026-10-07 | Two Canva embeds ('Calibri (MS)', 'Calibri (MS) Bold') both resolve to Calibri; reported twice | Canva | F006 | `canva_fonts` corner deck | One finding per family |
| 2026-10-07 | 'Montserrat SemiBold' with no Montserrat anywhere reported by both F003 and F007 | Design | F003, F007 | `test_f003_unavailable_family_left_to_f007` | F003 only when base family available; F007 owns "missing" |
| 2026-10-07 | python-pptx adds `<p:sldIdLst>` to a slideless deck just from reading `prs.slides` | Engine | All (Deck model) | `CORNER_DECKS['empty']` | Fixed in `Deck.slides` |
| 2026-10-06 | Slides that auto-advance on a timer during a show | General (David) | P001 | `p001_adv_after_5s` | Spec'd |
| 2026-10-06 | Videos set to play "When clicked on" or "In click sequence" instead of Automatically | General (David) | M001 | `media_modes/*` (capture from PowerPoint, Mac + Win) | Spec'd |
| 2026-10-06 | Need a per-slide list of embedded videos with durations | General (David) | M002 | `m002_two_videos_one_audio` | Spec'd |
| 2026-10-06 | Missing fonts that are free on Google Fonts should be downloadable/installable from the app | General (David) | F009 | `f009_montserrat_not_installed` | Spec'd |
| 2026-10-06 | Images are often placed past the slide edge on purpose; only text leaving the slide is a problem | General (David) | G001 | `g001_picture_off_slide_not_flagged` | Spec'd |
| 2026-10-06 | Text box starts at x = -0.56 in; centered text runs off the left edge on Mac (PAT slide 22) | Canva | G001 | `g001_text_box_negative_x` | Seen, fixed by hand |
| 2026-10-06 | Single-line titles have ~0.3% too little width; wrap to two lines in PowerPoint (PAT slides 5, 24) | Canva | L001 | `l001_title_zero_slack` | Seen, fixed by hand |
| 2026-10-06 | Every weight is its own fake family ("Calibri (MS) Bold") embedded in the regular slot; Mac substitutes fonts | Canva | F001, F002, F005 | `f001_bold_suffix`, `f005_misnamed_embed` | Seen, fixed by script |
| 2026-10-06 | File properties say "Microsoft Office PowerPoint" on a Canva export; app name can't identify source | Canva | X001 | `x001_canva_with_ppt_app_name` | Seen |
