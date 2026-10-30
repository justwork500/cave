# Scripts

Write a script once in PowerShell, Python or Bash, then run it from an automation, a routine, a dashboard button (through a routine) or the console. In this version, scripts run in CAVE's **sandbox**: a separate container (`cave-script-runner`) with PowerShell 7, Python 3 and Bash. It has no access to CAVE's own files or database, and no Docker socket. **Running scripts over SSH or on the CAVE host comes later.**

## Where scripts live

`config/scripts/<name>.ps1`, `.py` or `.sh`. Names use letters, digits, `.`, `-` and `_`. Automations refer to them as `ref: scripts/<name>`.

## The header

Every script starts with a `cave:` block. CAVE reads it to build the run form, check parameters and apply limits.

```powershell
<#
cave:
  name: Stop lab hosts
  timeout: 5m                 # 30s, 5m, 1h or HH:MM:SS; 60 s by default, 1 hour at most
  params:
    GraceSeconds: { type: int, default: 60, min: 0, max: 600 }
  secrets: [PROXMOX_TOKEN]
  sample: { status: "3 hosts stopped", stopped: 3 }   # what the Test Center pretends it returned
#>
param([int]$GraceSeconds = 60)
@{ status = "3 hosts stopped"; stopped = 3 } | ConvertTo-Json -Compress
```

```python
#!/usr/bin/env python3
# cave:
#   name: Check NAS backup age
#   params:
#     max_hours: { type: int, default: 26 }
import json, os
print(json.dumps({"status": "ok", "max": int(os.environ["CAVE_PARAM_MAX_HOURS"])}))
```

```bash
#!/usr/bin/env bash
# cave:
#   name: Disk space report
#   params:
#     warn_pct: { type: int, default: 85 }
set -euo pipefail
echo "{\"status\":\"ok\",\"warn\":$CAVE_PARAM_WARN_PCT}"
```

Parameter types are `int`, `float`, `str` and `bool`, with optional `default`, `min`, `max` and `choices`. A mistake in the header shows the file and line, like any other config file.

## The contract (the same for all three languages)

1. **Inputs:** each parameter arrives as an environment variable `CAVE_PARAM_<NAME>` and in one JSON object on standard input. PowerShell scripts also get them as named parameters.
2. **Secrets:** listed secrets arrive as environment variables. They're masked as `•••` everywhere CAVE shows output.
3. **Output:** the last line your script prints must be one JSON object. That becomes the step's result, for example `result_var: lab` makes `{{ lab.status }}` available to later steps. Anything printed before it goes to the run log.
4. **Result:** exit code 0 means success. Anything else fails the step and shows the last 20 lines of output.
5. **Timeout:** when it's reached, the script and everything it started are stopped.
6. **Run log:** who or what started it, the parameters (secrets masked), how long it took, the exit code and the output. CAVE keeps the last 100 runs per script.

**Parameters are never pasted into a command line.** They're passed as data, so a value like `"; rm -rf ~"` or `-Command evil` reaches your script as plain text and can't run anything.

## Secrets

Set each secret on the CAVE server as an environment variable named `CAVE_SECRET_<NAME>`, for example `CAVE_SECRET_PROXMOX_TOKEN` in Docker Compose's `.env` file. It never goes in `config/`. A script lists the secrets it needs under `secrets:`. **Only an Admin can save or delete a script that uses secrets**, because anyone who can edit a script could otherwise print the secret.

## Who can do what

- **Edit, test-run and see run logs:** anyone with the **Scripts** section in Users and permissions. By default, that's Admins and Operators.
- **Run a script directly:** whoever it's assigned to, as `script:<name>` in Users and permissions.
- **Use a script in an automation or routine:** you need to be able to run that script yourself.
- **Household members** run scripts through a dashboard button that starts a routine assigned to them.

## The Test Center

When you rehearse an automation in the Test Center, scripts don't run. Each step uses the script's `sample:` instead, unless you give a sample of your own in the request.

## Setting up the runner

CAVE talks to the runner using two environment variables, both set by the Docker Compose install:

- `CAVE_RUNNER_URL`, for example `http://script-runner:8099`
- `CAVE_RUNNER_TOKEN`, at least 32 random characters, shared with the runner

Without them, every script step fails with "The script runner isn't set up."
