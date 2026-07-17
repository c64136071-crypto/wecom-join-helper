# Troubleshooting

## Recognition Test Finds Nothing

1. Confirm WeCom is logged in and the intended group is the visible chat.
2. Scroll until the complete sign-up card and participation button are visible.
3. Use a short title keyword that is stable and unique to the intended card.
4. Keep the window still while the test runs.
5. Check the compatibility table for the currently verified WeCom version.

The test sends no mouse input. A missing result is safer than clicking an
uncertain card.

## Recognition Passes But Live Mode Is Disabled

Changing the keyword invalidates the previous recognition approval. Run Test
Recognition again with the new keyword, then enable live mode.

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

## Resetting First-Run Setup

Close Join Helper, rename its local `config.json`, and start it again. The
application creates a new safe configuration with live mode disabled. Keep the
old file private; do not attach it to a public issue.
