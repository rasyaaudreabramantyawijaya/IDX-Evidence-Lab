# AGENTS.md privacy control

`AGENTS.md` is project governance and must be treated as owner-controlled policy.

## Local control

- The file is locked with mode `0444`, so collaborators can read it but cannot
  write it through ordinary filesystem permissions.
- `scripts/protect-agents.sh edit` temporarily unlocks it only after checking
  the authorized owner UID and the configured public IPv4 address, then locks
  it again when the editor exits.
- The authorized IP is intentionally not guessed or committed. Configure it in
  the local, untracked `.agents-protection.env` file.

Setup:

```sh
cp .agents-protection.env.example .agents-protection.env
chmod 600 .agents-protection.env
# Replace AUTHORIZED_PUBLIC_IP with your current public IPv4.
chmod 755 scripts/protect-agents.sh
scripts/protect-agents.sh lock
scripts/protect-agents.sh verify
```

To edit:

```sh
scripts/protect-agents.sh edit
```

## Security boundary

An IP address is not proof of personal identity: it can change, be shared by
NAT, or be spoofed by a privileged local user. A person with administrator
access can also change permissions or edit the file directly. Therefore this
local control is a deterrent and audit aid, not an absolute privacy boundary.

For enforcement against collaborators, place the project in a Git host and
configure a protected default branch, require pull requests, enable signed
commits, and make `AGENTS.md` owned by a `CODEOWNERS` entry for your account.
The hosting service must also require your authenticated account for changes;
IP allowlisting may be added as a second factor, never as the sole identity
control.
