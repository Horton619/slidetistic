# The broken deck: what to break, one slide each

Build this in **PowerPoint**, once on the **Mac** and, if you can, again on a **Windows show PC**.
Save as `broken_mac.pptx` / `broken_win.pptx` and drop them in `corpus/`.

Rules that make it a perfect test deck:
- **One problem per slide.** Make the slide title the item number + name, e.g. "07 When Clicked On".
  Then SlideTistic's findings must line up slide by slide; anything else it reports is a false alarm.
- Any short video works (5–10 s .mp4 is plenty). Reuse the same one everywhere.
- Items marked ★ are things only real PowerPoint can tell us. Those matter most.

## Video and audio (the play-mode work)
| # | Slide | How to make it | Check |
|---|---|---|---|
| 01 | ★ When Clicked On | Insert video → Playback → Start: **When Clicked On** | M001 (blocks its fix) |
| 02 | ★ In Click Sequence | Insert video, leave Start: **In Click Sequence** | M001 must stay quiet |
| 03 | ★ Automatically | Insert video → Start: **Automatically** | M001 must stay quiet |
| 04 | ★ Click sequence after animations | Add a title with a Fly In on click, then a video set to In Click Sequence | M001 click count |
| 05 | ★ Rewind after playing | Video, tick **Rewind after Playing** | M002 (never seen yet) |
| 06 | ★ Loop + full screen + hide | Video, tick **Loop until Stopped**, **Play Full Screen**, **Hide While Not Playing** | M002 |
| 07 | ★ Trimmed | Video → **Trim Video**, cut a bit off both ends | M002 trimmed duration |
| 08 | ★ Muted | Video, Volume → **Mute** | M002 MUTED |
| 09 | ★ Audio across slides | Insert audio → **Play in Background** | M002 audio (never seen yet) |
| 10 | ★ Linked video | Insert → Video → This Device → **Link to File** (Mac: ▸ next to Insert) using a video on your Desktop | M003 |
| 11 | ★ Online video | Insert → Video → **Online Video**, paste any YouTube link | M005 |
| 12 | Risky format | Insert a .wmv or an iPhone HEVC .mov if you have one | M004 |

## Advancing and slide-show settings
| # | Slide | How to make it | Check |
|---|---|---|---|
| 13 | ★ Auto-advance | Transitions → After: **00:05**, keep On Mouse Click ticked | P001 |
| 14 | ★ Click advance off | Transitions → untick **On Mouse Click**, no timer | P002 |
| 15 | ★ Click animations | 3 bullet points appearing **On Click**, plus one **With Previous** | P005 click map (not built yet) |
| 16 | ★ Trigger animation | A shape that animates when *another* shape is clicked (Animation ▸ Trigger) | P005 |
| 17 | Hidden slide | Right-click the slide → **Hide Slide** | C004 |

Then **save a second copy** of the deck as `broken_showsettings_mac.pptx` with Slide Show ▸ Set Up Slide Show:
**Browsed at a kiosk**, **Loop continuously**, **Show without animation**, and Slides **from 2 to 5**. (P003; one copy is enough, these are deck-wide.)

## Text and layout
| # | Slide | How to make it | Check |
|---|---|---|---|
| 18 | Text off the left edge | Left-aligned text box dragged half off the left edge | G001 red + fix |
| 19 | Centered text box overhanging | Centered text box overhanging the right edge, words still on the slide | G001 yellow |
| 20 | Text below the bottom | Text box running off the bottom | G002 |
| 21 | Rotated text | Text box rotated 15° | G003 |
| 22 | Grouped text | Two text boxes + a shape, grouped | G004 |
| 23 | Picture off the slide | A photo bleeding off the edge (must NOT be flagged) | G001 stays quiet |

## Content
| # | Slide | How to make it | Check |
|---|---|---|---|
| 24 | Template text | A layout with "Click to add title" left empty, plus a box saying "Presented by [Speaker Name]" and "Venue: TBD" | C001 (empty placeholder must NOT be flagged; the typed ones must) |
| 25 | Placeholder slide | A slide that only says **VIDEO HERE** | C002 |
| 26 | Empty slide | A completely blank slide (no background picture) | C002 |
| 27 | ★ Comments | Add a review comment | C007 (unlocks its "remove comments" fix) |
| 28 | Links | A text link to a website, a picture linking to a website | P004 |
| 29 | Video link in notes | Speaker notes: "play this: https://youtu.be/…" | M006 |
| 30 | Emoji | A title with 🚀🎉 | F011 |

## Files and fonts
| # | Slide | How to make it | Check |
|---|---|---|---|
| 31 | ★ Linked Excel chart | Paste a chart from Excel with **Paste Special ▸ Paste Link** | X004 / X003 |
| 32 | Embedded Excel | Insert ▸ Object ▸ Excel spreadsheet | X003 |
| 33 | Missing font | Text in a font that's on your Mac but not a standard Office font (e.g. a Google font you installed) | F007 |
| 34 | Mac-only font | Text in **Avenir** or **Helvetica Neue** | F007 swap suggestion |
| 35 | Huge photo, small | A full-res phone photo shrunk to a thumbnail | M008 |
| 36 | Tiny logo, huge | A small logo stretched full-screen | M009 |

For F001/F002/F005 (fake bold font names, misfiled embeds) only **Canva** can make the real thing:
a Canva deck with a couple of fonts in bold, downloaded as .pptx, is the best test there.

## Also useful (any time)
- A **Google Slides** deck with a YouTube video inserted, downloaded as .pptx (M005, how Google really saves it).
- A **Keynote** deck exported to PowerPoint, with a video, a build, and Avenir text.
- A **clean, boring deck** that should come back with nothing to report.
