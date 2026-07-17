{{/*
Create the name of the service account to use
*/}}
{{- define "partnerApi.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "partnerApi.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image .Values.postgresCheckerInit.image) "global" .Values.global) -}}
{{- end -}}

{{/*
Render Env values section
*/}}
{{- define "partnerApi.baseEnvVars" -}}
{{- $context := .context -}}
{{- range $k, $v := .envVars }}
- name: {{ $k }}
{{- if or (kindIs "int64" $v) (kindIs "float64" $v) (kindIs "bool" $v) }}
  value: {{ $v | quote }}
{{- else if kindIs "string" $v }}
  value: {{ include "common.tplvalues.render" ( dict "value" $v "context" $context ) | squote }}
{{- else }}
  valueFrom: {{- include "common.tplvalues.render" ( dict "value" $v "context" $context ) | nindent 4}}
{{- end }}
{{- end }}
{{- end -}}

{{- define "partnerApi.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "partnerApi.baseEnvVars" (dict "envVars" $envVars "context" $) }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "benePortalApi.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "benePortalApi.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image .Values.postgresCheckerInit.image) "global" .Values.global) -}}
{{- end -}}

{{/*
Render Env values section
*/}}
{{- define "benePortalApi.baseEnvVars" -}}
{{- $context := .context -}}
{{- range $k, $v := .envVars }}
- name: {{ $k }}
{{- if or (kindIs "int64" $v) (kindIs "float64" $v) (kindIs "bool" $v) }}
  value: {{ $v | quote }}
{{- else if kindIs "string" $v }}
  value: {{ include "common.tplvalues.render" ( dict "value" $v "context" $context ) | squote }}
{{- else }}
  valueFrom: {{- include "common.tplvalues.render" ( dict "value" $v "context" $context ) | nindent 4}}
{{- end }}
{{- end }}
{{- end -}}

{{- define "benePortalApi.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "benePortalApi.baseEnvVars" (dict "envVars" $envVars "context" $) }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "staffPortalApi.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "staffPortalApi.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image .Values.postgresCheckerInit.image) "global" .Values.global) -}}
{{- end -}}

{{/*
Render Env values section
*/}}
{{- define "staffPortalApi.baseEnvVars" -}}
{{- $context := .context -}}
{{- range $k, $v := .envVars }}
- name: {{ $k }}
{{- if or (kindIs "int64" $v) (kindIs "float64" $v) (kindIs "bool" $v) }}
  value: {{ $v | quote }}
{{- else if kindIs "string" $v }}
  value: {{ include "common.tplvalues.render" ( dict "value" $v "context" $context ) | squote }}
{{- else }}
  valueFrom: {{- include "common.tplvalues.render" ( dict "value" $v "context" $context ) | nindent 4}}
{{- end }}
{{- end }}
{{- end -}}

{{- define "staffPortalApi.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "staffPortalApi.baseEnvVars" (dict "envVars" $envVars "context" $) }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "celeryBeatProducer.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "celeryBeatProducer.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image .Values.postgresCheckerInit.image) "global" .Values.global) -}}
{{- end -}}

{{/*
Render Env values section
*/}}
{{- define "celeryBeatProducer.baseEnvVars" -}}
{{- $context := .context -}}
{{- range $k, $v := .envVars }}
- name: {{ $k }}
{{- if or (kindIs "int64" $v) (kindIs "float64" $v) (kindIs "bool" $v) }}
  value: {{ $v | quote }}
{{- else if kindIs "string" $v }}
  value: {{ include "common.tplvalues.render" ( dict "value" $v "context" $context ) | squote }}
{{- else }}
  valueFrom: {{- include "common.tplvalues.render" ( dict "value" $v "context" $context ) | nindent 4}}
{{- end }}
{{- end }}
{{- end -}}

{{- define "celeryBeatProducer.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "celeryBeatProducer.baseEnvVars" (dict "envVars" $envVars "context" $) }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "celeryWorker.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "celeryWorker.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image .Values.postgresCheckerInit.image) "global" .Values.global) -}}
{{- end -}}

{{/*
Render Env values section
*/}}
{{- define "celeryWorker.baseEnvVars" -}}
{{- $context := .context -}}
{{- range $k, $v := .envVars }}
- name: {{ $k }}
{{- if or (kindIs "int64" $v) (kindIs "float64" $v) (kindIs "bool" $v) }}
  value: {{ $v | quote }}
{{- else if kindIs "string" $v }}
  value: {{ include "common.tplvalues.render" ( dict "value" $v "context" $context ) | squote }}
{{- else }}
  valueFrom: {{- include "common.tplvalues.render" ( dict "value" $v "context" $context ) | nindent 4}}
{{- end }}
{{- end }}
{{- end -}}

{{- define "celeryWorker.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "celeryWorker.baseEnvVars" (dict "envVars" $envVars "context" $) }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "staffPortalUi.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "staffPortalUi.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image) "global" .Values.global) -}}
{{- end -}}

{{/*
Render Env values section
*/}}
{{- define "staffPortalUi.baseEnvVars" -}}
{{- $context := .context -}}
{{- range $k, $v := .envVars }}
- name: {{ $k }}
{{- if or (kindIs "int64" $v) (kindIs "float64" $v) (kindIs "bool" $v) }}
  value: {{ $v | quote }}
{{- else if kindIs "string" $v }}
  value: {{ include "common.tplvalues.render" ( dict "value" $v "context" $context ) | squote }}
{{- else }}
  valueFrom: {{- include "common.tplvalues.render" ( dict "value" $v "context" $context ) | nindent 4}}
{{- end }}
{{- end }}
{{- end -}}

{{- define "staffPortalUi.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "staffPortalUi.baseEnvVars" (dict "envVars" $envVars "context" $) }}
{{- end -}}

{{/*
Sanity suite env — shared by the pm-seed, cm-seed, and test Jobs.
*/}}
{{- define "farmerRegistrySanity.env" -}}
- name: SANITY_PARTNER_BASE_URL
  value: {{ tpl .Values.sanity.partnerBaseUrl $ | quote }}
- name: SANITY_VERIFY_TLS
  value: {{ .Values.sanity.verifyTls | quote }}
- name: SANITY_RUN_E2E
  value: {{ .Values.sanity.runE2e | quote }}
- name: SANITY_FAIL_ON_ERROR
  value: {{ .Values.sanity.failOnError | quote }}
- name: SANITY_READINESS_TIMEOUT
  value: {{ .Values.sanity.readinessTimeout | quote }}
- name: SANITY_CONTROLLER_ID
  value: {{ .Values.sanity.controllerId | quote }}
- name: SANITY_CM_AUDIENCE
  value: {{ .Values.sanity.cmAudience | quote }}
- name: SANITY_DCI_SENDER_ID
  value: {{ .Values.sanity.dciSenderId | quote }}
- name: SANITY_DCI_RECEIVER_ID
  value: {{ .Release.Name | quote }}
- name: SANITY_DCI_REG_TYPE
  value: {{ .Values.sanity.regType | quote }}
- name: SANITY_DCI_REG_RECORD_TYPE
  value: {{ .Values.sanity.regRecordType | quote }}
- name: SANITY_DCI_SEARCH_TEXT
  value: {{ .Values.sanity.searchText | quote }}
- name: SANITY_DATA_SCOPES
  value: {{ .Values.sanity.dataScopes | quote }}
- name: SANITY_DENIED_SCOPES
  value: {{ .Values.sanity.deniedScopes | quote }}
- name: SANITY_FARMER_REGISTER_ID
  value: {{ .Values.sanity.farmerRegisterId | quote }}
- name: SANITY_CR_TAB_ID
  value: {{ .Values.sanity.crTabId | quote }}
- name: SANITY_CR_SECTION_ID
  value: {{ .Values.sanity.crSectionId | quote }}
- name: SANITY_AWE_SETTLE_TIMEOUT
  value: {{ .Values.sanity.aweSettleTimeout | quote }}
- name: SANITY_AUDIT_TIMEOUT
  value: {{ .Values.sanity.auditTimeout | quote }}
# Registry staff-portal-api — the change-request e2e logs in as REAL demo users
# via the password grant. The registry's Keycloak client is a browser OIDC
# client with no service account, and the users keycloak-init provisions
# (alex.carter, nina.patel) are already the approvers the shipped AWE policy
# names — so nothing extra has to be created in Keycloak or seeded into AWE.
- name: SANITY_STAFF_BASE_URL
  value: {{ include "common.tplvalues.render" (dict "value" .Values.sanity.staffBaseUrl "context" $) | quote }}
- name: SANITY_STAFF_TOKEN_URL
  value: "{{ tpl .Values.global.keycloakIssuerUrl $ }}/protocol/openid-connect/token"
- name: SANITY_STAFF_CLIENT_ID
  value: {{ include "common.tplvalues.render" (dict "value" .Values.global.authClientId "context" $) | quote }}
- name: SANITY_STAFF_CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ include "common.tplvalues.render" (dict "value" .Values.global.authClientSecret "context" $) | quote }}
      key: {{ .Values.global.authClientSecretKey | quote }}
      optional: true
# The suite's OWN Keycloak identity. keycloak-init's demo users cannot be used:
# it sets their password as temporary, so Keycloak forces UPDATE_PASSWORD and
# the password grant fails with "Account is not fully set up".
- name: SANITY_STAFF_USERNAME
  value: {{ .Values.sanity.staffUsername | quote }}
- name: SANITY_STAFF_PASSWORD
  value: {{ .Values.sanity.staffPassword | quote }}
- name: SANITY_STAFF_ROLES
  value: {{ .Values.sanity.staffRoles | quote }}
- name: SANITY_MAX_APPROVAL_ROUNDS
  value: {{ .Values.sanity.maxApprovalRounds | quote }}
# Keycloak admin — used ONLY to provision the test user above with a
# non-temporary password and to guarantee directAccessGrantsEnabled on the
# client (neither is expressible in keycloak-init's realms schema).
- name: SANITY_KEYCLOAK_BASE_URL
  value: {{ tpl (index .Values "keycloak-init" "keycloak" "url") $ | quote }}
- name: SANITY_KEYCLOAK_REALM
  value: {{ tpl .Values.global.keycloakRealm $ | quote }}
- name: SANITY_KEYCLOAK_ADMIN_USER
  value: {{ (index .Values "keycloak-init" "keycloak" "user") | quote }}
- name: SANITY_KEYCLOAK_ADMIN_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ tpl (index .Values "keycloak-init" "keycloak" "existingSecret") $ | quote }}
      key: {{ (index .Values "keycloak-init" "keycloak" "existingSecretKey") | quote }}
      optional: true
# Registry DB — inject the sanity farmer, and read it back to assert the change
# request was applied and that version history was written.
- name: SANITY_REGISTRY_PGHOST
  value: {{ .Values.global.postgresqlHost | quote }}
- name: SANITY_REGISTRY_PGPORT
  value: {{ .Values.global.registryDBPort | default 5432 | quote }}
- name: SANITY_REGISTRY_PGDATABASE
  value: {{ include "common.tplvalues.render" (dict "value" .Values.global.registryDB "context" $) | quote }}
- name: SANITY_REGISTRY_PGUSER
  value: {{ include "common.tplvalues.render" (dict "value" .Values.global.registryDBUser "context" $) | quote }}
- name: SANITY_REGISTRY_PGPASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "common.tplvalues.render" (dict "value" .Values.global.registryDBSecret "context" $) | quote }}
      key: {{ include "common.tplvalues.render" (dict "value" .Values.global.registryDBUserPasswordKey "context" $) | quote }}
      optional: true
# AWE DB — register the sanity user as an approver on the shipped policy.
- name: SANITY_AWE_PGHOST
  value: {{ .Values.global.postgresqlHost | quote }}
- name: SANITY_AWE_PGPORT
  value: {{ .Values.global.aweDBPort | default 5432 | quote }}
- name: SANITY_AWE_PGDATABASE
  value: {{ include "common.tplvalues.render" (dict "value" .Values.global.aweDB "context" $) | quote }}
- name: SANITY_AWE_PGUSER
  value: {{ include "common.tplvalues.render" (dict "value" .Values.global.aweDBUser "context" $) | quote }}
- name: SANITY_AWE_PGPASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "common.tplvalues.render" (dict "value" .Values.global.aweDBSecret "context" $) | quote }}
      key: {{ include "common.tplvalues.render" (dict "value" .Values.global.aweDBUserPasswordKey "context" $) | quote }}
      optional: true
# Audit DB — Audit Manager has NO query API (ingest + health only), so the
# audit assertion reads its table directly.
- name: SANITY_AUDIT_PGHOST
  value: {{ include "common.tplvalues.render" (dict "value" (.Values.sanity.auditDbHost | default .Values.global.postgresqlHost) "context" $) | quote }}
- name: SANITY_AUDIT_PGPORT
  value: {{ .Values.sanity.auditDbPort | default 5432 | quote }}
- name: SANITY_AUDIT_PGDATABASE
  value: {{ include "common.tplvalues.render" (dict "value" .Values.sanity.auditDb "context" $) | quote }}
- name: SANITY_AUDIT_PGUSER
  value: {{ include "common.tplvalues.render" (dict "value" .Values.sanity.auditDbUser "context" $) | quote }}
- name: SANITY_AUDIT_PGPASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "common.tplvalues.render" (dict "value" .Values.sanity.auditDbSecret "context" $) | quote }}
      key: {{ include "common.tplvalues.render" (dict "value" .Values.sanity.auditDbUserPasswordKey "context" $) | quote }}
      optional: true
# Partner Management — key servability check + admin seed (staff-portal-api).
- name: SANITY_PM_PARTNER_API_URL
  value: {{ tpl .Values.global.partnerManagementApiUrl $ | quote }}
- name: SANITY_PM_ADMIN_URL
  value: {{ tpl .Values.global.partnerManagementAdminApiUrl $ | quote }}
# Authenticate to PM's admin API AS PM's own admin client (holds partner_manager).
- name: SANITY_PM_ADMIN_TOKEN_URL
  value: "{{ tpl .Values.global.keycloakIssuerUrl $ }}/protocol/openid-connect/token"
- name: SANITY_PM_ADMIN_CLIENT_ID
  value: {{ tpl .Values.global.pmSeedClientId $ | quote }}
- name: SANITY_PM_ADMIN_CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ tpl .Values.global.pmSeedClientId $ | quote }}
      key: client_secret
      optional: true
# Consent Manager — staff-portal-api (binding+policy seed) + admin token.
- name: SANITY_CM_STAFF_URL
  value: {{ tpl .Values.global.consentManagerStaffUrl $ | quote }}
- name: SANITY_CM_AUTH_ENABLED
  value: "true"
- name: SANITY_CM_TOKEN_URL
  value: "{{ tpl .Values.global.keycloakIssuerUrl $ }}/protocol/openid-connect/token"
- name: SANITY_CM_CLIENT_ID
  value: {{ tpl .Values.global.consentManagerAuthClientId $ | quote }}
# The CM Keycloak client's secret. Must hold CONSENT_MANAGER_ADMIN (for the CM
# binding) and partner_manager (for the PM key seed — pm_seed falls back to
# these creds). Optional: absent → the e2e seed is skipped, not failed.
- name: SANITY_CM_CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ tpl .Values.global.consentManagerAuthClientId $ | quote }}
      key: client_secret
      optional: true
{{- end -}}
