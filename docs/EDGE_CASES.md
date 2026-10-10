# Edge cases log

One entry per "oh by the way". Newest first.

| Date | What was seen | Source | Check | Fixture | Status |
| --- | --- | --- | --- | --- | --- |
| 2026-10-10 | Box-edge clamp moved an indented bullet block 1.8 in under an illustration (PAT 18) | PAT | fit.grow / plan_fit | `test_plan_never_slides_text_onto_a_picture` | Text-based checks; no box clamp |
| 2026-10-10 | Narrowing a tall block added lines, last line off the slide (PAT 17) | PAT | L008 | `test_plan_never_predicts_text_off_the_slide` | Predict re-wrap; slide edge absolute |
| 2026-10-10 | Canva images are image-filled freeforms, not pictures; a push slid bullets under a chart (PAT 5) | Canva | fit.is_graphic | `test_image_filled_shapes_count_as_graphics_but_plain_panels_dont` | Fixed |
| 2026-10-10 | Header wrap after font fix (1→2 lines) must count as broken | David | L001 | — (needs layout) | New check, fix on |
| 2026-10-10 | Original render matched no lines for a box → "was 0 lines" false alarm (PAT 26) | PAT | runner baseline | — | Unmatched = unknown |
| 2026-10-10 | Layout fixes flagged but didn't fix: L010's fix() was pasted inside a helper and never ran | Engine | L010 + contract test | `test_metadata_valid` (fix must be on the class) | Fixed |
| 2026-10-10 | Safe-zone nudge moved titles onto the text below (PAT 5, 9); widening a column hit the next column (PAT 24) | PAT | L008, L009 | `test_search_rejects_widths_that_hit_other_text`, `test_l008_pushes_the_text_below_when_it_has_room` | Collision prediction + push |
| 2026-10-10 | Widening re-wraps every line, not just the orphan: new orphans/collisions | PAT | fit.Reflow | `test_reflow_reproduces_the_breaks_it_was_calibrated_on` | Whole-box re-wrap prediction |
| 2026-10-10 | Shared words ("Health" in title and body) and pdftotext lines merged across boxes put text in the wrong box | PAT 5 | layout.pdf.assign | — | Reading-order matching |
| 2026-10-10 | Exact nudge to the safe line rendered "0.0 in" over | PAT 9, 22 | L008 | — | Land slightly inside |
| 2026-10-10 | DOI/URL tail on its own line counted as orphan ("01508-3") | PAT 29 | L009 | `test_l009_flags_lonely_last_word_but_not_a_broken_doi` | Exempt |
| 2026-10-10 | Renderer opened its copy "after.pptx" while David had his own "after.pptx" open; PowerPoint returned HIS deck, which was exported as the 'after' image and then closed (unsaved, test copy) | Mac PowerPoint | render.py | — | Unique copy names + active-presentation path check |
| 2026-10-09 | "When Clicked On" = self-trigger only, no click-sequence play step (8 videos, Mac + Win); identical to click-sequence save minus the main-sequence block | Dropbox corpus | M001 | `media_modes/*_when_clicked.xml`, `test_m001_fix_matches_powerpoints_own_click_sequence` | Detect red + fix, **on** (David verified in PowerPoint 2026-10-10) |
| 2026-10-09 | Mac: play/pause toggle (presetID 2) in the click sequence; 1 video | Dropbox corpus | M001 | `media_modes/mac_toggle_in_sequence.xml` | Reported "check by hand" |
| 2026-10-09 | "Tilda Sans Extra Bold" read as "Tilda Sans Extra" + bold | Dropbox corpus | F001 | `test_f001_extra_bold_is_not_bold` | Fixed |
| 2026-10-09 | Folders named "*.pptx" holding slide JPEGs; a deck with a corrupt image inside (Bad CRC) | Dropbox | CLI | `test_cli_explains_folder_named_pptx` | Plain-English errors |
| 2026-10-09 | pytest kept repaired copies of every corpus deck: 15 GB | Dev | tests | pytest.ini | No retention; copies deleted per deck |
| 2026-10-09 | Shows are clicker-driven: only "When Clicked On" (and no start setting) is a problem; target is "In Click Sequence", not "Automatically" | David | M001 | `test_m001_click_sequence_and_automatic_are_fine` | Detect only; fix waits for a real "When Clicked On" save |
| 2026-10-09 | Visual review: report outlines drawn over text hid first letters, so correct text looked cut off (PAT slide 17) | Report | report.py | manual (corpus PAT) | Outlines now outside shapes |
| 2026-10-09 | Bullets indented (marL/indent) put words on-slide although the box starts 0.81 in off the left (PAT slide 18) | Canva | G001 | `test_g001_indented_bullets_are_not_certain` | Fixed: indent + inset aware |
| 2026-10-09 | Box overhangs 0.04–0.14 in past top with centered text: nothing cut (PAT) | Canva | G001 | `test_g001_overhang_within_inner_margin_ignored` | Fixed |
| 2026-10-09 | Font fixes touched 26 PAT slides but only ~11 look different | Report | visual.py | manual | Identical renders fold into one line |
| 2026-10-09 | Keynote videos set to volume 0 (play silent) in a real deck | Mac PowerPoint | M002 | `test_m002_muted_video_called_out` | Inventory shows MUTED |
| 2026-10-09 | Walk-in deck: every slide advTm 15 s, clicks off; business deck: 28–64 s leftover timings on 4 slides | Win PowerPoint | P001 | `test_p001_*` | Detect; one finding per deck |
| 2026-10-09 | PowerPoint PDF export skips hidden slides; page numbers must skip them too | Mac PowerPoint | visual.py | — | Mapped |
| 2026-10-09 | Port 8765 on David's Mac is used by another app; report preview server uses 8799 | Dev | .claude/launch.json | — | Noted |
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
