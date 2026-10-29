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
