# Edge cases log

One entry per "oh by the way". Newest first.

| Date | What was seen | Source | Check | Fixture | Status |
| --- | --- | --- | --- | --- | --- |
| 2026-10-09 | **PAT MBD sign-off:** automatic repair matches the hand-made MacFix exactly (210 runs + embedded list); opens in Mac PowerPoint | Canva | F001–F008 | corpus: PAT MBD | Phase 1 signed off |
| 2026-10-09 | Google export files **Arial** under 'Google Sans' / 'Gothic A1' / 'Helvetica' as a stand-in; F006 removed it as "Office font", leaving the text fontless (re-scan flagged "introduced by F006") | Google | F006, F005 | `test_f006_keeps_arial_standing_in_for_another_font`, `test_f005_explains_exporter_stand_in` | Fixed: F006 goes by listed name; F005 explains |
| 2026-10-09 | Embeds listed under names the text uses ('SN Pro 1 Extra-Light' holding SN Pro; 'League Spartan' regular slot holding bold) — re-filing would disconnect working fonts on Windows | Various | F005 | `test_f005_never_renames_an_embed_the_text_still_uses`, `test_f005_bold_file_in_regular_slot_of_same_name_left_alone` | Fixed: only re-file when text no longer uses the old name |
| 2026-10-09 | PowerPoint (Mac and Win) compresses **every** embedded font: 101/101 in corpus. Compression isn't a warning sign | PowerPoint | F008 | `test_f008_compressed_and_editable_embeds_not_flagged` | F008 now licence-flag only |
| 2026-10-09 | Aptos (Office default) in 24/51 decks; M365 cloud fonts and Windows fonts aren't "missing" | Office | F007 | `test_f007_cloud_and_windows_fonts_are_yellow` | Yellow tier via `conditional_fonts.yaml` |
| 2026-10-09 | Walk-in/out slides have no shapes but show a background or layout artwork (16 false "empty" slides) | Various | C002 | `test_c002_walk_in_slide_with_background_image_is_not_empty` | Fixed |
| 2026-10-09 | Low-res noise: 1.33× stretch flagged 173 images; reference slides with many citation links | Various | M009, P004 | thresholds; `test_p004_one_finding_per_slide_listing_links` | M009: 2× stretch and ≥480 px wide; P004: one per slide |
| 2026-10-09 | Google exports a YouTube video as a thumbnail picture linking to YouTube; needs internet at venue | Google (David) | M005 | `test_m005_google_style_picture_linking_to_youtube` | Detect only |
| 2026-10-09 | Video/file links in slides and speaker notes need fetching before the show; crew have a YouTube downloader, so list only | David | M006 | `test_m006_links_in_text_notes_and_hyperlinks` | Detect only, retrieval list |
| 2026-10-09 | Unfinished decks: "Click to add title", "Lorem ipsum", "[Name]", "Video here" slides | David | C001, C002 | `test_c001_*`, `test_c002_*` | Detect only |
| 2026-10-09 | Tier 1+2 research batch: hidden slides, links leaving the show, aspect ratio, Mac-only fonts, emoji, image size/res/format, file hygiene, OLE/ActiveX/macros, local-path links, comments | Research | C004 P004 G006 F007 F011 M008 M009 M011 X002 X003 X004 C007 | `tests/checks/test_*` | Detect only |
| 2026-10-09 | python-pptx `image.content_type` sniffs bytes; PowerPoint uses the declared part type (an EMF part was reported as PNG) | Engine | M011 (core/images.py) | `test_m011_emf_flagged` | Fixed |
| 2026-10-09 | AppleScript "save as PNG" on Mac PowerPoint reports success but writes nothing; "save as PDF" works (~1 s) | Mac PowerPoint | Visual review | spike | Use PDF + pdftoppm |
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
