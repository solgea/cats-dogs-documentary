# Manual YouTube upload

## Boundary

There is no YouTube API integration, OAuth client, upload command, scheduler, or
automatic publishing in this repository. Publishing is a manual action by a
human editor. The archive is review material, not a statement that anything was
uploaded.

## Preconditions

Do not upload until all of the following are true:

- [ ] The package QA status is `PASS` (or every `WARN` has a written disposition).
- [ ] A real MP4 exists at the recorded path and passed local media validation.
- [ ] The file is 1080x1920, 9:16, 30–60 seconds, with audible narration and
      readable captions.
- [ ] A human has watched the entire render, including the last frame and audio.
- [ ] Every source has been opened and checked against the citation.
- [ ] The narration matches the final audio; no line was changed during rendering.
- [ ] The generated animal anatomy is coherent. Reject extra limbs, tails, ears,
      eyes, merged hands, impossible gaits, or uncanny mouth motion.
- [ ] No scene manufactures distress, punishment, aggression, or a false "guilty"
      or "sad" emotion for engagement.
- [ ] The description carries the synthetic-media disclosure, educational
      disclaimer, `Sources:` section, and `#Shorts`.
- [ ] The title is accurate and under the length limit.
- [ ] Human editorial sign-off has been recorded in the team's approval record.

The batch's `package.json` files intentionally remain at
`human_review_required: true` and `human_signoff: false` until the formal review
is complete. Editing that JSON is not itself evidence of review, and the
pre-render QA gate continues to require the false value. Do not flip fields to
manufacture `publish_ready: true`; use the project's editorial approval process
and update the pipeline deliberately if a sign-off workflow is added.

## Upload checklist

1. Open YouTube Studio for the correct channel.
2. Upload the validated MP4 as a Short. Keep the native vertical file; do not let
   a horizontal file be cropped or letterboxed by a conversion step.
3. Use the generated `metadata.json` title and description. Verify the text on
   screen and in the description one last time.
4. Confirm visibility. The default is `private`. Keep it private until final
   sign-off; publish manually only when the editor is satisfied.
5. Keep `made_for_kids` false, matching the channel policy.
6. Check the Shorts preview, captions, audio mix, and end card.
7. Do not add a claim, source, quote, statistic, or medical instruction that is
   absent from the reviewed package.
8. If YouTube requires a synthetic/altered-content disclosure, follow the current
   platform UI and the channel's disclosure text. The description always includes:
   `Illustrative, AI-assisted visuals; not documentary footage.`
9. Upload manually. Do not automate the final publish action.

## After upload

The current metadata schema keeps `youtube_video_id: null`,
`youtube_url: null`, and `upload_status: "not_uploaded_manual_only"`. This reflects
the absence of upload integration. If a future operator records the video id, do
so in a separate editorial record or extend the schema deliberately; do not
silently rewrite a generated artifact and then re-hash it as if nothing changed.

Suggested record (maintained outside this repository until a supported workflow
exists):

```text
package_id:
batch_id:
render_sha256:
youtube_video_id:
uploaded_at:
uploaded_by:
visibility:
human_signoff:
source_spot_check:
welfare_review:
notes:
```

## If something is wrong

- **Wrong citation:** stop, fix the source/claim, rebuild, re-render if narration
  changed, and review again.
- **Malformed animal:** reject the render. Do not publish a "close enough" shot.
- **Audio/caption mismatch:** fix the request and re-render; do not patch captions
  only in YouTube if the burned-in text is wrong.
- **Overclaim or medical advice:** rewrite the narration and metadata, re-run QA,
  and re-render as needed.
- **Missing disclosure:** do not upload. Regenerate metadata after correcting the
  package.
- **Accidental public upload:** set the video private immediately and notify the
  editorial owner.
