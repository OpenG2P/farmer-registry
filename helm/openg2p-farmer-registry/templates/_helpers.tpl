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
# Partner Management — key servability check + admin seed (staff-portal-api).
- name: SANITY_PM_PARTNER_API_URL
  value: {{ tpl .Values.global.partnerManagementApiUrl $ | quote }}
- name: SANITY_PM_ADMIN_URL
  value: {{ tpl .Values.global.partnerManagementAdminApiUrl $ | quote }}
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
