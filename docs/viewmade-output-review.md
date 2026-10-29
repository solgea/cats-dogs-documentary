# ViewMade Output Review

## What the provider actually returns

The official `viewmade_create_short` metadata describes a 42–55 second vertical
documentary Short built from **verified real moving footage**, with footage
sources and attribution lines. Ready jobs inspected in the connected account
were 1440x2560, 45–49 seconds, with 17–21 scenes assembled from multiple YouTube
clips.

This is not the same artifact described by the previous local package plan:

| Previous local plan | ViewMade output |
| --- | --- |
| 1080x1920 | 1440x2560 (normalized locally to 1080x1920) |
| Six planned scenes | 17–21 edited scenes |
| One continuous animal subject | Multiple clips and often multiple animals |
| AI-assisted illustrative visuals | Real third-party footage |
| Local SRT cues | Provider-generated spoken-word captions |
| Local title/description/tags | Provider title/description/tags plus sources |

ViewMade does not accept a shot list, source checklist, or visual plan. It
selects footage per narrative beat. A `style_hint` can set a broad tone, but it
cannot guarantee a single continuous animal.

## Pilot review: `dog-guilty-look`

The first paid pilot completed on 2026-10-28. It is a valid local MP4, but it is
**not editorially approved**.

| Field | Observed value |
| --- | --- |
| Provider job | `f59f8a91-7b2b-4dbb-a03d-62effc911581` |
| Local file | `renders/dog-guilty-look.mp4`, 26,401,159 bytes |
| Media | 47.733 s, 1080x1920 after normalization, H.264 + AAC stereo |
| Provider title | “The truth behind the guilty look” |
| Provider tags | `guilty`, `look` |
| Provider description | “That famous 'guilty look' your dog gives you isn't actually remorse—it's a survival tactic to calm you down.” |
| Scenes | 21 |
| Credits | 20 charged, 0 refunded; balance tool still returns `internal_error` |
| Source list | Six YouTube entertainment/compilation clips |

The six footage sources are from Fluffies, Wild+Derp, The Pet Collective, Rumble
Viral, and Denver the Guilty Dog. The provider's `sources` field documents the
**clips used for the edit**, not a peer-reviewed research bibliography; no
veterinary institution, university, welfare organization, or study is listed.
The local research record remains the only verified evidence base, and the
provider's narration does not follow it:

- The local script centers on the 2009 owner-cue/scolding experiment and says
  the look tracked the owner's cues, not a reliable inner sense of guilt.
- The provider captions sampled at 4 fps (OCR, approximate and incomplete) build
  a broader “appeasement response” and “social hierarchy” narrative: “assume
  pets feel moral remorse when they break a rule”, “a simple case of regret
  behavior”, “actually an appeasement response”, “a biological signal, not a
  moral one”, “their place [in the] social hierarchy”.
- The provider `subject_note` says the request's premise is unsupported by the
  research and that the video tells the supported version. That is a material
  subject change, not a minor wording change.

Frame review also found multiple different dogs, hard cuts between unrelated
clips, low-light doorway/shed footage, visible watermark text (`wildplusderp`),
and clips from the staged “guilty dog” entertainment genre. This conflicts with
the local six-scene, continuous-subject, species-correct visual plan. The
burned-in captions are word-by-word and change too quickly for comfortable
reading; the local SRT was not used.

The old metadata disclosure (“Illustrative, AI-assisted visuals; not documentary
footage.”) was false for this output because the pilot uses real third-party
footage. The channel policy has since been changed to the real-footage disclosure,
and this pilot is marked `REJECTED`; it must not be published.

## Second pilot review: `cat-sweetness`

The second paid pilot completed on 2026-10-29. It is a valid local MP4 and passes
the technical render gates, but it is **not editorially approved**.

| Field | Observed value |
| --- | --- |
| Provider job | `74955fe4-199a-49e3-bf8c-305d7ba0c36c` |
| Local file | `renders/cat-sweetness.mp4`, 28,526,396 bytes |
| SHA-256 | `7bcdfa60f237f1e670cf525a8367f51e81dee7e10bd54b10dec0f43ae273459c` |
| Media | 43.833 s, 1080x1920 after normalization, H.264 + AAC stereo |
| Provider title | “The Sugar-Blind Predator” |
| Provider tags | `T1R2+3`, `sweetness`, `receptor` |
| Provider description | “A genetic mutation turned cats into obligate carnivores that are biologically blind to sugar.” |
| Scenes | 18 (local plan: six) |
| Credits | 20 charged, 0 refunded, net 20 |
| Source list | Four YouTube clips: Mr. RandomVideo, Oxford Academic, Science Magazine, Natural History Museum |

Technical QA is sound: the artifact is 1080x1920 with audio, the duration is
within the Shorts limit, all four provider source URLs appear in the description,
and `render.attribution` passes. The remaining problem is editorial.

Sampled frames and captions show a different script and a weaker visual argument
than the approved local package:

- At 0.5 s a red arrow annotation from the source clip points into an orange
  cat's head; the caption is “CAT”.
- At 4 s the cat is eating grass while the caption says “SUGAR”.
- At 8 s the caption is “ENERGY-RICH”; at 20 s sugar cubes are captioned
  “RECEPTORS”; at 24 s a histology slide is captioned “TO”; at 32 s a laboratory
  technician is captioned “BIOLOGICAL”.
- From about 36 s to the end, the same cat-eating-grass clip repeats. Captions in
  that tail include “THEM”, “CAT”, “RODENTS”, “TO”, “STORES”, “CAT”, “SUGAR”,
  “IS”, and “INVISIBLE”.
- At 40.0 s there is a chromatic-aberration transition with red/green fringing
  and vertical edge lines.

The provider's own description reverses the causal claim: cats were already
obligate carnivores, and the Tas1r2 pseudogene explains the loss of sweet taste,
not the origin of carnivory. The captions contain terms such as “GENETIC”,
“ENERGY-RICH”, “MICROSCOPIC BIOLOGICAL ARCHITECTURE”, “RODENTS TO STORES”, and
“CAT SUGAR IS INVISIBLE” that do not appear in the approved local script. The
local SRT remains the researched narration; the provider re-authored the story
and did not use it.

No corner watermark was detected in the sampled frames at 2, 10, 18, 26, 34, and
42 s, but the video contains laboratory, histology, and sugar-cube footage that
is not represented by the four provider-reported source URLs. The provider also
returned no clip-level `clips` mapping (`clips: 0` in the status payload), so the
provenance of those shots cannot be checked from the package. Attribution covers
only the sources the provider reported; it does not establish a licence or prove
that every visual is accounted for.

**Recommendation: reject for publication.** The render is retained as evidence,
but it must not be published, and no further paid render should be submitted
without a new explicit approval.

## Consequences

1. **Do not call a real-footage render "AI-assisted."** The channel now uses the
   real-footage disclosure by default, and QA rejects an AI-assisted claim in
   real-footage metadata.
2. **Attribution lines are mandatory.** The provider returns `sources` and
   `attributions`. YouTube publication must include the attribution lines in the
   description.
3. **Continuity and welfare need frame-level review.** Multiple animals, changing
   coats, low-quality source clips, captions over faces, or distressed behavior
   are editorial failures even when the MP4 parses correctly.
4. **The local SRT is not the provider caption track.** Check the burned-in
   captions against the narration and the local script before approving.
5. **`COMPLETE` means the file exists and passes media checks.** It does not mean
   the video is editorially approved or publication-ready.

## Decision recorded: 2026-10-29

The channel owner chose **real-footage montage** as the channel format.

- The pilot is **rejected for publication** because of entertainment/compilation
  sources, multiple dogs, visible watermarks, and a narrative that diverges from
  the local evidence record.
- The channel disclosure, visual policy, metadata schema, and QA gates now use a
  real-footage standard and require every provider source URL in the description.
- The next step is one new pilot from a single package, using the local script
  and `engine: clearcut`. The remaining packages stay unrendered until that pilot
  is reviewed.
- Attribution is not a licence. A human must confirm the provider's clip rights
  before publication.

The batch remains `PARTIAL` with one validated MP4 and one rejected package; it
is never `publish_ready` without a future approved render and human sign-off.
