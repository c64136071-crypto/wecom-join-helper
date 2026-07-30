# Troubleshooting

## Monitoring Finds Nothing

1. Confirm WeCom is logged in and the intended group is the visible chat.
2. Scroll until the complete sign-up card and participation button are visible.
3. Use a short title keyword that is stable and unique to the intended card.
4. Keep the complete WeCom window visible while monitoring runs.
5. Check the compatibility table for the currently verified WeCom version.

Join Helper pauses while WeCom is minimized or covered by another window. A
missing result is safer than clicking an uncertain card.

## Monitoring Does Not Restart

Stop and application relaunch both leave monitoring idle. Click Start again
after opening the intended group.

## Unsafe State After Attempt

Do not immediately restart the application. First inspect the visible WeCom
document to determine whether the row was inserted. This status means the
application may have sent the insertion action and deliberately refused to
retry.

## Windows Shows Unknown Publisher

Early builds are unsigned. Download only from this repository's Releases page,
verify the SHA-256 sidecar, and keep Windows security controls enabled. If the
checksum does not match, delete the download and report the release asset.

## Where Settings And Logs Live

- Installed build: `%LOCALAPPDATA%\WeComJoinHelper`
- Portable build: `data` inside the extracted JoinHelper folder

Logs rotate locally and omit full OCR titles, group names, and user names. When
opening an issue, quote only the minimal generic error and remove any data that
identifies a person or organization.

## Resetting Settings

Close Join Helper, rename its local `config.json`, and start it again. The
application creates a new default configuration. Keep the old file private; do
not attach it to a public issue.
