# Visual Templates

The runtime requires four tightly cropped PNG templates:

- `yellow_icon.png`: generic yellow checked icon on a group sign-up card.
- `participate.png`: participation control on the visible card.
- `join.png`: blue document control that inserts the current WeCom identity.
- `submit.png`: blue edit-state confirmation control shown after insertion.

Templates must contain no user name, group title, company identifier, message
content, or full-screen capture. The detector matches across a bounded range of
scales, but major WeCom redesigns can still require reviewed replacement assets.

Recognition test mode verifies the card title and visual candidate without
sending mouse input. Live mode remains disabled until that test succeeds.
