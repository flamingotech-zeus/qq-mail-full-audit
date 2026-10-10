# QQ Mail Full Audit

[English](README.md) | [简体中文](README.zh-CN.md)

> Cross-validate QQ Mail through MCP, IMAP and POP3 to get past the usual 30-day and 4-folder limits, and actually read the mailbox to the bottom.

## What this is

This is not a "count your unread mail" script. Counting is the easy part and it is also where most tools quietly lie to you.

The problem it solves is a mismatch. A third-party connector shows you the last 30 days across four folders. The phone app shows "380+ unread". Those two numbers describe different sets, and the gap is not a bug — it is a protocol and interface limitation. This skill makes that gap explicit before it draws any conclusion.

## Why we open-sourced it

We use this internally whenever mail needs to be accounted for — before a trip, when a deadline list has to be trusted, or when something important was almost certainly missed.

The reason it is worth publishing: nearly every tool in this space stops at the limit of one connector and reports the number as if it were the total. That is the failure mode we wanted to design out. It contains no business data of ours, so there is nothing to strip before sharing.

## What it does

- **Three-channel cross-validation.** MCP connector, IMAP and POP3 are queried separately, and the results are compared rather than merged into one optimistic number.
- **Full folder coverage.** Five folders, read and unread, instead of the four-folder ceiling the connector imposes.
- **modified-UTF-7 decoding.** IMAP encodes non-ASCII folder names with a modified UTF-7 variant. Without decoding it, folders with Chinese names simply do not resolve.
- **Read-only retrieval.** Messages are fetched without being marked as read. Your unread state stays exactly as it was.
- **Boundary documentation.** Each channel's real capability is written down, including what it cannot reach and why.
- **Eight documented pitfalls** collected while building this, each with the symptom and the fix.

## Requirements

Python 3 · a QQ Mail IMAP authorization code (not your login password)

## Installation

```bash
git clone https://github.com/<your-username>/qq-mail-full-audit.git
```

Then place the folder into your agent skills directory:

| OS | Path |
|---|---|
| Windows | `C:\Users\<you>\.workbuddy\skills\qq-mail-full-audit\` |
| macOS / Linux | `~/.workbuddy/skills/qq-mail-full-audit/` |

There is no build step. Restart the session and it takes effect.

## How to use

Ask the question you actually have:

- "Check my mailbox — how many are unread?"
- "Go through all unread mail and list the ones that need action"
- "I think I missed something important, dig through the whole mailbox"

The skill establishes the delivery boundary first, then queries all three channels, then reports what was found and what remained out of reach.

## Files

```
├── SKILL.md
└── scripts/
    ├── qqmail_alldims_audit.py
    ├── qqmail_fetch_bodies.py
    └── qqmail_imap_pull.py
```

## Notes and limits

1. **The gap is real and cannot be closed by better code.** POP3 is a download-oriented protocol with its own state model; IMAP has server-side folder semantics; the MCP connector has its own window. Reporting one number as the truth is the mistake.
2. **Authorization code, not password.** QQ Mail requires a separate IMAP authorization code. Using the login password will fail, and that is the correct behaviour.
3. **Read-only by design.** There is no option to mark messages as read from this tool. That is deliberate.
4. **Rate limits apply.** Querying a large mailbox aggressively will get throttled by the provider.

## License

MIT
