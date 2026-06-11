{{/*
Release-name length guard.

Several resources created by this chart (and its subcharts, especially
postgres-init Jobs) embed the release name and a release-derived DB name
in their `metadata.name`. Kubernetes auto-injects `batch.kubernetes.io/job-name`
as a Pod label whose VALUE is limited to 63 characters. With our naming
pattern, release names longer than 30 characters can produce Job names that
exceed this limit, causing `helm install` to fail mid-way with a cryptic
"spec.template.labels: Invalid value: ..." error.

This guard fails the install upfront with a clear, actionable message.

If you absolutely must use a longer release name, override the DB names
explicitly (global.registryDB, global.idGeneratorDB, etc.) to be shorter
than the defaults — the SHA-suffix pattern in values.yaml is designed to
stay within budget but requires a release name <= 30 chars.
*/}}

{{- define "openg2p-registry.validateReleaseName" -}}
{{/*
  $maxLen comes from the worst-case Job name in the chart, namely the
  id-generator's postgres-init Job:

      <release>-idgen-pg-init-<release>-idgenerator
      └─ release + 14 ─┘  └─ release + 12 ─────┘   (separators included)

  Total = 2 * len(release) + 27. For the auto-injected
  `batch.kubernetes.io/job-name` Pod label (max 63 chars), we need:
      2 * len(release) + 27 <= 63   →   len(release) <= 18

  We use 18 as a hard cap. If you ever shorten the DB names or the
  `idgenerator.postgres-init.nameOverride`, this cap can be relaxed.
*/}}
{{- $maxLen := 18 -}}
{{- if gt (len .Release.Name) $maxLen -}}
{{- $msg := printf "\n\nERROR: Helm release name %q is %d characters long.\nMaximum supported length is %d characters.\n\nKubernetes enforces a 63-character limit on label values. The release name appears in resource names (e.g. postgres-init Jobs) and indirectly in the auto-injected `batch.kubernetes.io/job-name` label. With this chart's DB-name template, release names longer than %d chars produce Job names that exceed the 63-char ceiling and cause `helm install` to fail with `spec.template.labels: Invalid value: ... must be no more than 63 characters`.\n\nFix: re-run `helm install` with a shorter release name (e.g. `registry`, `farmer-reg`)." .Release.Name (len .Release.Name) $maxLen $maxLen -}}
{{- fail $msg -}}
{{- end -}}
{{- end -}}
