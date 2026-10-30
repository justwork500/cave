<#
cave:
  name: Stop lab hosts
  target: sandbox
  timeout: 5m
  params:
    GraceSeconds: { type: int, default: 60, min: 0, max: 600 }
  sample: { status: "3 hosts stopped", stopped: 3 }
#>
param([int]$GraceSeconds = 60)
Write-Output "Stopping lab hosts with $GraceSeconds s grace..."
@{ status = "3 hosts stopped"; stopped = 3 } | ConvertTo-Json -Compress
